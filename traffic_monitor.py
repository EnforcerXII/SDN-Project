"""
SDN Traffic Monitor - POX Controller
Course: COMPUTER NETWORKS - UE24CS252B

Place this file at:  pox/ext/traffic_monitor.py

Run with:
    python3 pox.py log.level --DEBUG traffic_monitor

Description:
    A POX OpenFlow controller that acts as a learning switch while
    monitoring and logging all traffic flows. Tracks:
      - Per-host packet/byte counts
      - Per-flow statistics (src, dst, protocol)
      - High-volume sender alerts
      - Periodic summary every 10 seconds
"""

import collections
import datetime
import logging
import os

import pox.openflow.libopenflow_01 as of
from pox.core import core
from pox.lib.addresses import EthAddr
from pox.lib.packet import arp, ethernet, icmp, ipv4, tcp, udp
from pox.lib.recoco import Timer
from pox.lib.util import dpid_to_str

log = core.getLogger()

# ── Config ────────────────────────────────────────────────────────────────────
LOG_FILE = "traffic_log.txt"
ALERT_PACKET_THRESHOLD = 100  # packets sent before alert
STATS_INTERVAL = 10  # seconds between summary prints

# ── File logger ───────────────────────────────────────────────────────────────
_fh = logging.FileHandler(LOG_FILE)
_fh.setFormatter(
    logging.Formatter("%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%H:%M:%S")
)
log.logger.addHandler(_fh)
log.logger.setLevel(logging.DEBUG)


def _ts():
    return datetime.datetime.now().strftime("%H:%M:%S")


def _proto_name(pkt):
    """Return a human-readable protocol string for a parsed packet."""
    if pkt.find("arp"):
        return "ARP"
    ip = pkt.find("ipv4")
    if ip:
        if pkt.find("icmp"):
            return "ICMP"
        if pkt.find("tcp"):
            return "TCP"
        if pkt.find("udp"):
            return "UDP"
        return f"IPv4(proto={ip.protocol})"
    return "ETH"


class TrafficMonitorSwitch(object):
    """Per-switch state + logic."""

    def __init__(self, connection):
        self.connection = connection
        self.dpid = connection.dpid

        # mac → port
        self.mac_to_port = {}

        # (eth_src, eth_dst, proto) → {packets, bytes, first_seen, last_seen}
        self.flow_stats = {}

        # mac → {packets_in, packets_out, bytes_in, bytes_out}
        self.host_stats = collections.defaultdict(
            lambda: {"packets_in": 0, "packets_out": 0, "bytes_in": 0, "bytes_out": 0}
        )

        self.alerted = set()

        connection.addListeners(self)

        # Periodic summary timer
        Timer(STATS_INTERVAL, self._print_summary, recurring=True)

        log.info("=" * 60)
        log.info(f"  [SWITCH] Connected  dpid={dpid_to_str(self.dpid)}")
        log.info(f"  Log file : {os.path.abspath(LOG_FILE)}")
        log.info(f"  Alert threshold : {ALERT_PACKET_THRESHOLD} packets/host")
        log.info("=" * 60)

    # ── Packet-in ─────────────────────────────────────────────────────────────

    def _handle_PacketIn(self, event):
        pkt = event.parsed
        if not pkt.parsed:
            log.warning("Ignoring incomplete packet")
            return

        pkt_in = event.ofp
        in_port = pkt_in.in_port
        eth_src = str(pkt.src)
        eth_dst = str(pkt.dst)
        pkt_len = len(pkt_in.data) if pkt_in.data else 0
        proto = _proto_name(pkt)

        # ── Learn ─────────────────────────────────────────────────────────
        if eth_src not in self.mac_to_port:
            log.info(f"[LEARN]  {eth_src} → port {in_port}")
        self.mac_to_port[eth_src] = in_port

        # ── Determine output port ─────────────────────────────────────────
        out_port = (
            self.mac_to_port[eth_dst] if eth_dst in self.mac_to_port else of.OFPP_FLOOD
        )

        # ── Host stats ────────────────────────────────────────────────────
        self.host_stats[eth_src]["packets_out"] += 1
        self.host_stats[eth_src]["bytes_out"] += pkt_len
        self.host_stats[eth_dst]["packets_in"] += 1
        self.host_stats[eth_dst]["bytes_in"] += pkt_len

        # ── Flow stats ────────────────────────────────────────────────────
        key = (eth_src, eth_dst, proto)
        now = datetime.datetime.now()
        if key not in self.flow_stats:
            self.flow_stats[key] = {
                "packets": 0,
                "bytes": 0,
                "first_seen": now,
                "last_seen": now,
            }
            log.info(
                f"[FLOW]   NEW  {eth_src} → {eth_dst}  "
                f"proto={proto}  port={in_port}→{out_port}"
            )
        fs = self.flow_stats[key]
        fs["packets"] += 1
        fs["bytes"] += pkt_len
        fs["last_seen"] = now

        # ── Alert ─────────────────────────────────────────────────────────
        total_out = self.host_stats[eth_src]["packets_out"]
        if total_out > ALERT_PACKET_THRESHOLD and eth_src not in self.alerted:
            log.warning(
                f"[ALERT]  High traffic from {eth_src}: {total_out} packets sent!"
            )
            self.alerted.add(eth_src)

        # ── Install flow rule (only when we know the port) ────────────────
        if out_port != of.OFPP_FLOOD:
            msg = of.ofp_flow_mod()
            msg.match.in_port = in_port
            msg.match.dl_src = EthAddr(eth_src)
            msg.match.dl_dst = EthAddr(eth_dst)
            msg.priority = 1
            msg.idle_timeout = 30
            msg.hard_timeout = 0
            msg.actions.append(of.ofp_action_output(port=out_port))
            # Include buffered packet if available
            if pkt_in.buffer_id != of.NO_BUFFER:
                msg.buffer_id = pkt_in.buffer_id
            else:
                msg.data = pkt_in.data
            self.connection.send(msg)
            return  # already forwarded via flow mod

        # ── Flood (unknown destination) ───────────────────────────────────
        msg = of.ofp_packet_out()
        msg.actions = [of.ofp_action_output(port=of.OFPP_FLOOD)]
        msg.data = pkt_in
        msg.in_port = in_port
        self.connection.send(msg)

    # ── Periodic summary ──────────────────────────────────────────────────────

    def _print_summary(self):
        sep = "-" * 60
        log.info(sep)
        log.info(f"[STATS]  Periodic summary  ({_ts()})")

        log.info("  HOST STATS:")
        log.info(
            f"  {'MAC':<20} {'Pkts Out':>10} {'Bytes Out':>12} "
            f"{'Pkts In':>10} {'Bytes In':>12}"
        )
        for mac, s in self.host_stats.items():
            log.info(
                f"  {mac:<20} {s['packets_out']:>10} {s['bytes_out']:>12} "
                f"{s['packets_in']:>10} {s['bytes_in']:>12}"
            )

        log.info("  FLOW TABLE:")
        for (src, dst, proto), fs in self.flow_stats.items():
            duration = (fs["last_seen"] - fs["first_seen"]).seconds
            log.info(
                f"  {src} → {dst}  [{proto}]  "
                f"pkts={fs['packets']}  bytes={fs['bytes']}  "
                f"duration={duration}s"
            )
        log.info(sep)


# ── POX component entry point ─────────────────────────────────────────────────


class TrafficMonitor(object):
    """Listens for new switch connections and spawns a per-switch monitor."""

    def __init__(self):
        core.openflow.addListeners(self)
        log.info("SDN Traffic Monitor ready — waiting for switches...")

    def _handle_ConnectionUp(self, event):
        log.info(f"Switch connected: {dpid_to_str(event.dpid)}")
        TrafficMonitorSwitch(event.connection)


def launch():
    """POX entry point — called by pox.py."""
    core.registerNew(TrafficMonitor)
    log.info("Traffic Monitor component launched.")
