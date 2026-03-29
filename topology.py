#!/usr/bin/env python3
"""
SDN Traffic Monitor - Mininet Topology (POX version)
Course: COMPUTER NETWORKS - UE24CS252B

Topology:
        [POX Controller :6633]
                |
          [s1 — OVS Switch]
         /    |    \    \
       h1    h2    h3    h4
  10.0.0.1   .2    .3    .4

Usage (after POX is running):
    sudo python3 topology.py
"""

import time

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSSwitch, RemoteController


def build_network():
    setLogLevel("info")

    net = Mininet(
        controller=RemoteController,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True,
    )

    info("\n*** Adding controller (POX on localhost:6633)\n")
    c0 = net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=6633,  # POX default port
    )

    info("*** Adding switch\n")
    s1 = net.addSwitch("s1", protocols="OpenFlow10")  # POX uses OF 1.0

    info("*** Adding hosts\n")
    h1 = net.addHost("h1", ip="10.0.0.1/24", mac="00:00:00:00:00:01")
    h2 = net.addHost("h2", ip="10.0.0.2/24", mac="00:00:00:00:00:02")
    h3 = net.addHost("h3", ip="10.0.0.3/24", mac="00:00:00:00:00:03")
    h4 = net.addHost("h4", ip="10.0.0.4/24", mac="00:00:00:00:00:04")

    info("*** Creating links (100 Mbps, 5ms delay)\n")
    for host in [h1, h2, h3, h4]:
        net.addLink(host, s1, bw=100, delay="5ms")

    info("*** Starting network\n")
    net.build()
    c0.start()
    s1.start([c0])

    info("\n*** Waiting for controller handshake...\n")
    time.sleep(3)

    # ── Scenario 1: Basic connectivity ────────────────────────────────────────
    info("\n" + "=" * 60 + "\n")
    info("SCENARIO 1: Basic Connectivity Test (pingall)\n")
    info("=" * 60 + "\n")
    net.pingAll()

    # ── Scenario 2: Targeted ICMP ─────────────────────────────────────────────
    info("\n" + "=" * 60 + "\n")
    info("SCENARIO 2: Targeted ping  h1 → h3  (10 packets)\n")
    info("=" * 60 + "\n")
    result = h1.cmd("ping -c 10 10.0.0.3")
    info(result)

    # ── Scenario 3: TCP throughput ────────────────────────────────────────────
    info("\n" + "=" * 60 + "\n")
    info("SCENARIO 3: TCP throughput  h2 (server) ↔ h4 (client)\n")
    info("=" * 60 + "\n")
    h2.cmd("iperf -s &")
    time.sleep(1)
    result = h4.cmd("iperf -c 10.0.0.2 -t 5")
    info(result)
    h2.cmd("kill %iperf")

    # ── Scenario 4: UDP burst (triggers alert) ────────────────────────────────
    info("\n" + "=" * 60 + "\n")
    info("SCENARIO 4: UDP burst  h1 → h2  (triggers high-traffic alert)\n")
    info("=" * 60 + "\n")
    h2.cmd("iperf -s -u &")
    time.sleep(1)
    result = h1.cmd("iperf -c 10.0.0.2 -u -b 10M -t 5")
    info(result)
    h2.cmd("kill %iperf")

    info("\n*** All scenarios complete — dropping into CLI\n")
    info("    Try: pingall | h1 ping -c3 h3 | nodes | net | dump\n\n")

    CLI(net)

    info("*** Stopping network\n")
    net.stop()


if __name__ == "__main__":
    build_network()
