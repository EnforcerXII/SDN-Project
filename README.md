# SDN Traffic Monitor
**Course:** COMPUTER NETWORKS – UE24CS252B  
**Controller:** Ryu (OpenFlow 1.3)  
**Topology:** 1 switch · 4 hosts  

---

## Problem Statement

Design and implement an SDN-based Traffic Monitor using Mininet and a Ryu OpenFlow 1.3 controller. The controller acts as a **learning switch** while simultaneously **monitoring, logging, and analysing all network flows** in real time. It detects high-volume senders and logs per-host and per-flow statistics periodically.

---

## Topology

```
        [Ryu Controller :6653]
                 |
           [s1 — OVS Switch]
          /    |    \    \
        h1    h2    h3    h4
   10.0.0.1  .2   .3    .4
```

All links: 100 Mbps, 5 ms delay.

---

## Features

| Feature | Description |
|---|---|
| Learning switch | Learns MAC→port dynamically, installs flow rules |
| Flow logging | Logs every new flow (src, dst, protocol, ports) |
| Host stats | Tracks packets/bytes in+out per host |
| Periodic summary | Prints full host+flow table every 10 seconds |
| High-traffic alert | Warns when a host sends > 100 packets |
| Flow expiry logging | Logs stats when idle flow rules expire (30s timeout) |
| Dual output | Logs to both terminal and `traffic_log.txt` |

---

## Setup & Execution

### Prerequisites

**Ubuntu / Debian:**
```bash
sudo apt update && sudo apt install -y mininet openvswitch-switch python3-pip
pip install ryu
```

**Arch Linux:**
```bash
sudo pacman -S mininet openvswitch python-pip
pip install ryu
# Start OVS manually:
sudo systemctl start ovsdb-server ovs-vswitchd
```

### Run (automated)

```bash
git clone <your-repo-url>
cd sdn-traffic-monitor
bash run.sh
```

This will:
1. Start Open vSwitch
2. Clean old Mininet state
3. Launch Ryu controller (background)
4. Run all 4 test scenarios automatically
5. Drop into Mininet CLI for manual exploration

### Run (manual, two terminals)

**Terminal 1 — Ryu controller:**
```bash
ryu-manager traffic_monitor.py --ofp-tcp-listen-port 6653 --verbose
```

**Terminal 2 — Mininet topology:**
```bash
sudo python3 topology.py
```

---

## Test Scenarios

### Scenario 1 — Basic Connectivity (`pingall`)
All 4 hosts ping each other. Verifies the learning switch works and flow rules are installed correctly.

**Expected output:**
```
*** Results: 0% dropped (12/12 received)
```

### Scenario 2 — Targeted ICMP (`h1 → h3`, 10 packets)
Verifies per-flow logging for ICMP. The controller logs the new flow and tracks packet/byte count.

**Expected output:**
```
[FLOW]   NEW  00:00:00:00:00:01 → 00:00:00:00:00:03  proto=ICMP  port=1→3
10 packets transmitted, 10 received, 0% packet loss
```

### Scenario 3 — TCP Throughput (`h2` server ↔ `h4` client, 5s)
Uses `iperf` to generate TCP traffic. Verifies flow stats tracking for TCP flows and measures bandwidth.

**Expected output:**
```
[FLOW]   NEW  ... proto=TCP ...
[Client] Transfer: ~590 MB  Bandwidth: ~940 Mbits/sec
```

### Scenario 4 — UDP Burst (`h1 → h2`, 10 Mbps, 5s)
Generates enough UDP packets to exceed the alert threshold (100 packets), triggering:

**Expected output:**
```
[ALERT]  High traffic from 00:00:00:00:00:01: 1XX packets sent!
```

---

## Expected Log Output (traffic_log.txt)

```
10:01:00  INFO      ============================================================
10:01:00  INFO        SDN Traffic Monitor Controller started
10:01:02  INFO      [SWITCH] Connected  dpid=0x0000000000000001
10:01:04  INFO      [LEARN]  host 00:00:00:00:00:01 is on port 1 (dpid=1)
10:01:04  INFO      [FLOW]   NEW  00:00:00:00:00:01 → 00:00:00:00:00:02  proto=ICMP  port=1→2
10:01:10  INFO      ------------------------------------------------------------
10:01:10  INFO      [STATS]  Periodic summary  (10:01:10)
10:01:10  INFO        HOST STATS:
10:01:10  INFO        MAC                  Pkts Out    Bytes Out    Pkts In    Bytes In
10:01:10  INFO        00:00:00:00:00:01          14         1176         14        1176
...
10:01:10  WARNING   [ALERT]  High traffic from 00:00:00:00:00:01: 101 packets sent!
```

---

## File Structure

```
sdn-traffic-monitor/
├── traffic_monitor.py   # Ryu controller — all SDN logic
├── topology.py          # Mininet topology + automated test scenarios
├── run.sh               # One-shot launcher script
└── README.md
```

---

## SDN Concepts Demonstrated

- **packet_in** events: Controller receives unknown packets and decides forwarding
- **match–action**: Flow rules match on (in_port, eth_src, eth_dst) and output to learned port
- **flow rule installation**: `OFPFlowMod` with priority=1, idle_timeout=30s
- **table-miss entry**: Priority=0 catch-all sends everything to controller initially
- **flow expiry**: `OFPFlowRemoved` events log stats when rules time out
- **OpenFlow 1.3**: Full OF 1.3 feature set via OVS

---

## References

1. Mininet overview — https://mininet.org/overview/
2. Mininet walkthrough — https://mininet.org/walkthrough/
3. Ryu documentation — https://ryu.readthedocs.io/en/latest/
4. OpenFlow 1.3 specification — https://opennetworking.org/wp-content/uploads/2014/10/openflow-spec-v1.3.0.pdf
5. Ryu source (GitHub) — https://github.com/faucetsdn/ryu
