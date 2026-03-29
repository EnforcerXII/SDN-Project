# SDN Traffic Monitor
**Course:** COMPUTER NETWORKS – UE24CS252B  
**Controller:** POX (OpenFlow 1.0)  
**Topology:** 1 switch · 4 hosts  

---

## Problem Statement

Design and implement an SDN-based Traffic Monitor using Mininet and a POX OpenFlow controller. The controller acts as a **learning switch** while simultaneously **monitoring, logging, and analysing all network flows** in real time. It detects high-volume senders and logs per-host and per-flow statistics periodically.

---

## Topology

```
      [POX Controller :6633]
               |
         [s1 — OVS Switch]
        /    |    \    \
      h1    h2    h3    h4
 10.0.0.1   .2    .3    .4
```

All links: 100 Mbps, 5 ms delay.

---

## Features

| Feature | Description |
|---|---|
| Learning switch | Learns MAC→port dynamically, installs flow rules |
| Flow logging | Logs every new flow (src, dst, protocol) |
| Host stats | Tracks packets/bytes in+out per host |
| Periodic summary | Prints full host+flow table every 10 seconds |
| High-traffic alert | Warns when a host sends > 100 packets |
| Dual output | Logs to both terminal and `traffic_log.txt` |

---

## Setup & Execution

### Prerequisites (Ubuntu 22.04)

```bash
# Mininet + OVS
sudo apt update && sudo apt install -y mininet

# POX (no pip needed — just clone)
git clone https://github.com/noxrepo/pox ~/pox
```

That's it. No pip installs, no dependency hell.

### Run (automated — recommended)

```bash
git clone <your-repo-url>
cd sdn-traffic-monitor
bash run.sh
```

`run.sh` will automatically:
1. Find your POX installation
2. Copy `traffic_monitor.py` into POX's `ext/` folder
3. Clean old Mininet state
4. Start POX controller in the background
5. Run all 4 test scenarios
6. Drop into Mininet CLI

### Run (manual — two terminals)

**Terminal 1 — copy controller and start POX:**
```bash
cp traffic_monitor.py ~/pox/ext/
cd ~/pox
python3 pox.py log.level --DEBUG traffic_monitor
```

Wait until you see:
```
INFO:traffic_monitor:SDN Traffic Monitor ready — waiting for switches...
```

**Terminal 2 — start Mininet:**
```bash
sudo mn -c                     # clean up first
sudo python3 topology.py
```

---

## Test Scenarios

### Scenario 1 — Basic Connectivity (`pingall`)
All 4 hosts ping each other. Verifies the learning switch installs flow rules correctly.

**Expected output:**
```
*** Results: 0% dropped (12/12 received)
```

### Scenario 2 — Targeted ICMP (`h1 → h3`, 10 packets)
Verifies per-flow ICMP logging.

**Expected output:**
```
[FLOW]   NEW  00:00:00:00:00:01 → 00:00:00:00:00:03  proto=ICMP  port=1→3
10 packets transmitted, 10 received, 0% packet loss
```

### Scenario 3 — TCP Throughput (`h2` server ↔ `h4` client, 5s iperf)
Generates TCP traffic, verifies flow stats tracking and measures bandwidth.

**Expected output:**
```
[FLOW]   NEW  ... proto=TCP ...
Bandwidth: ~940 Mbits/sec
```

### Scenario 4 — UDP Burst (`h1 → h2`, 10 Mbps, 5s)
Generates enough UDP packets to exceed the alert threshold.

**Expected output:**
```
[ALERT]  High traffic from 00:00:00:00:00:01: 1XX packets sent!
```

---

## Expected Log (traffic_log.txt)

```
10:01:00  INFO      ============================================================
10:01:00  INFO        [SWITCH] Connected  dpid=00-00-00-00-00-00-00-01
10:01:04  INFO      [LEARN]  00:00:00:00:00:01 → port 1
10:01:04  INFO      [FLOW]   NEW  00:00:00:00:00:01 → 00:00:00:00:00:02  proto=ICMP  port=1→2
10:01:10  INFO      ------------------------------------------------------------
10:01:10  INFO      [STATS]  Periodic summary  (10:01:10)
10:01:10  INFO        HOST STATS:
10:01:10  INFO        MAC                  Pkts Out    Bytes Out    Pkts In    Bytes In
10:01:10  INFO        00:00:00:00:00:01          14         1176         14        1176
...
10:01:42  WARNING   [ALERT]  High traffic from 00:00:00:00:00:01: 101 packets sent!
```

---

## File Structure

```
sdn-traffic-monitor/
├── traffic_monitor.py   # POX controller — all SDN logic
├── topology.py          # Mininet topology + 4 automated test scenarios
├── run.sh               # One-shot launcher
└── README.md
```

---

## SDN Concepts Demonstrated

- **packet_in events**: Unknown packets sent to controller for decision
- **match–action**: Flow rules match on (in_port, eth_src, eth_dst) → output port
- **flow rule installation**: `ofp_flow_mod` with priority=1, idle_timeout=30s
- **flooding**: Unknown destinations flooded until MAC is learned
- **OpenFlow 1.0**: Via POX + OVS

---

## References

1. Mininet overview — https://mininet.org/overview/
2. Mininet walkthrough — https://mininet.org/walkthrough/
3. POX wiki — https://noxrepo.github.io/pox-doc/html/
4. POX source — https://github.com/noxrepo/pox
5. OpenFlow 1.0 spec — https://opennetworking.org/wp-content/uploads/2013/04/openflow-spec-v1.0.0.pdf
