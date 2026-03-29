"""
SDN Traffic Monitor - Ryu Controller
Course: COMPUTER NETWORKS - UE24CS252B
Description:
    A Ryu-based OpenFlow 1.3 controller that acts as a learning switch
    while monitoring and logging all traffic flows. It tracks:
      - Per-host packet/byte counts
      - Flow-level statistics (src, dst, protocol, packet count)
      - Alerts for high-volume traffic (potential flood/DoS detection)
      - Periodic stats polling from the switch
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, tcp, udp, icmp, arp
from ryu.lib import hub

import datetime
import collections
import logging
import os

# ── Logging setup ────────────────────────────────────────────────────────────
LOG_FILE = "traffic_log.txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)
logger = logging.getLogger("TrafficMonitor")

# ── Thresholds ────────────────────────────────────────────────────────────────
ALERT_PACKET_THRESHOLD = 100   # packets/host before alert
STATS_POLL_INTERVAL    = 10    # seconds between flow-stat polls


class TrafficMonitor(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # mac_to_port[dpid][mac] = port
        self.mac_to_port = {}

        # flow_stats[dpid][(eth_src, eth_dst, proto)] = {packets, bytes, first_seen, last_seen}
        self.flow_stats = collections.defaultdict(dict)

        # host_stats[mac] = {packets_in, packets_out, bytes_in, bytes_out}
        self.host_stats = collections.defaultdict(
            lambda: {"packets_in": 0, "packets_out": 0,
                     "bytes_in":   0, "bytes_out":   0}
        )

        # alerted hosts (so we don't spam)
        self.alerted = set()

        # start background polling thread
        self.monitor_thread = hub.spawn(self._stats_poller)

        logger.info("=" * 60)
        logger.info("  SDN Traffic Monitor Controller started")
        logger.info(f"  Log file : {os.path.abspath(LOG_FILE)}")
        logger.info(f"  Alert threshold : {ALERT_PACKET_THRESHOLD} packets/host")
        logger.info(f"  Stats poll every: {STATS_POLL_INTERVAL}s")
        logger.info("=" * 60)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _ts(self):
        return datetime.datetime.now().strftime("%H:%M:%S")

    def _proto_name(self, eth_type, ip_proto=None):
        if eth_type == 0x0806:
            return "ARP"
        if eth_type == 0x0800:
            if ip_proto == 6:  return "TCP"
            if ip_proto == 17: return "UDP"
            if ip_proto == 1:  return "ICMP"
            return f"IPv4(proto={ip_proto})"
        return f"ETH({hex(eth_type)})"

    def _add_flow(self, datapath, priority, match, actions, idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod  = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )
        datapath.send_msg(mod)

    # ── Switch handshake ──────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser

        # table-miss: send everything to controller
        match   = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, priority=0, match=match, actions=actions)

        logger.info(f"[SWITCH] Connected  dpid={datapath.id:#018x}")

    # ── Packet-in handler ─────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg      = ev.msg
        datapath = msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser
        dpid     = datapath.id
        in_port  = msg.match["in_port"]

        pkt     = packet.Packet(msg.data)
        eth_pkt = pkt.get_protocol(ethernet.ethernet)
        if eth_pkt is None:
            return

        eth_src  = eth_pkt.src
        eth_dst  = eth_pkt.dst
        eth_type = eth_pkt.ethertype

        # ── Learn MAC → port ──────────────────────────────────────────────
        self.mac_to_port.setdefault(dpid, {})
        if eth_src not in self.mac_to_port[dpid]:
            logger.info(f"[LEARN]  host {eth_src} is on port {in_port} (dpid={dpid})")
        self.mac_to_port[dpid][eth_src] = in_port

        # ── Determine output port ─────────────────────────────────────────
        out_port = (self.mac_to_port[dpid][eth_dst]
                    if eth_dst in self.mac_to_port[dpid]
                    else ofproto.OFPP_FLOOD)

        # ── Identify protocol ─────────────────────────────────────────────
        ip_proto  = None
        ip4       = pkt.get_protocol(ipv4.ipv4)
        if ip4:
            ip_proto = ip4.proto

        proto_name = self._proto_name(eth_type, ip_proto)
        pkt_len    = len(msg.data)

        # ── Update host stats ─────────────────────────────────────────────
        self.host_stats[eth_src]["packets_out"] += 1
        self.host_stats[eth_src]["bytes_out"]   += pkt_len
        self.host_stats[eth_dst]["packets_in"]  += 1
        self.host_stats[eth_dst]["bytes_in"]    += pkt_len

        # ── Update flow stats ─────────────────────────────────────────────
        flow_key = (eth_src, eth_dst, proto_name)
        now      = datetime.datetime.now()
        if flow_key not in self.flow_stats[dpid]:
            self.flow_stats[dpid][flow_key] = {
                "packets":    0,
                "bytes":      0,
                "first_seen": now,
                "last_seen":  now,
            }
            logger.info(
                f"[FLOW]   NEW  {eth_src} → {eth_dst}  "
                f"proto={proto_name}  port={in_port}→{out_port}"
            )
        fs = self.flow_stats[dpid][flow_key]
        fs["packets"]   += 1
        fs["bytes"]     += pkt_len
        fs["last_seen"]  = now

        # ── Alert on high-traffic hosts ───────────────────────────────────
        total_out = self.host_stats[eth_src]["packets_out"]
        if total_out > ALERT_PACKET_THRESHOLD and eth_src not in self.alerted:
            logger.warning(
                f"[ALERT]  High traffic from {eth_src}: "
                f"{total_out} packets sent!"
            )
            self.alerted.add(eth_src)

        # ── Install flow rule (skip flood so we don't lock in the wrong port)
        actions = [parser.OFPActionOutput(out_port)]
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=eth_dst, eth_src=eth_src)
            # idle_timeout=30: rule removed after 30s of inactivity
            self._add_flow(datapath, priority=1, match=match,
                           actions=actions, idle_timeout=30)

        # ── Forward the packet ────────────────────────────────────────────
        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out  = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)

    # ── Periodic stats poller ─────────────────────────────────────────────────

    def _stats_poller(self):
        """Background thread: polls switch flow stats every N seconds."""
        while True:
            hub.sleep(STATS_POLL_INTERVAL)
            self._print_summary()

    def _print_summary(self):
        sep = "-" * 60
        logger.info(sep)
        logger.info(f"[STATS]  Periodic summary  ({self._ts()})")

        # Host table
        logger.info("  HOST STATS:")
        logger.info(f"  {'MAC':<20} {'Pkts Out':>10} {'Bytes Out':>12} {'Pkts In':>10} {'Bytes In':>12}")
        for mac, s in self.host_stats.items():
            logger.info(
                f"  {mac:<20} {s['packets_out']:>10} {s['bytes_out']:>12} "
                f"{s['packets_in']:>10} {s['bytes_in']:>12}"
            )

        # Flow table
        logger.info("  FLOW TABLE:")
        for dpid, flows in self.flow_stats.items():
            for (src, dst, proto), fs in flows.items():
                duration = (fs["last_seen"] - fs["first_seen"]).seconds
                logger.info(
                    f"  {src} → {dst}  [{proto}]  "
                    f"pkts={fs['packets']}  bytes={fs['bytes']}  "
                    f"duration={duration}s"
                )
        logger.info(sep)

    # ── Flow-removed event ────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPFlowRemoved, MAIN_DISPATCHER)
    def flow_removed_handler(self, ev):
        msg  = ev.msg
        match = msg.match
        logger.info(
            f"[EXPIRED] Flow removed  pkts={msg.packet_count}  "
            f"bytes={msg.byte_count}  match={dict(match)}"
        )
