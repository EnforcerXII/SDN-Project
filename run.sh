#!/bin/bash
# run.sh — Launch the SDN Traffic Monitor project
# Usage: bash run.sh
# Requires: ryu-manager, mn (mininet), sudo

set -e

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║    SDN Traffic Monitor — UE24CS252B      ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Check dependencies ────────────────────────────────────────────────────────
check_cmd() {
    if ! command -v "$1" &>/dev/null; then
        echo "[ERROR] '$1' not found. $2"
        exit 1
    fi
}

check_cmd ryu-manager  "Install with: pip install ryu"
check_cmd mn           "Install with: sudo pacman -S mininet  OR  sudo apt install mininet"
check_cmd ovs-vsctl    "Install Open vSwitch: sudo pacman -S openvswitch"

# ── Ensure OVS is running (Arch needs manual start) ───────────────────────────
echo "[*] Starting Open vSwitch services..."
sudo systemctl start ovsdb-server 2>/dev/null || true
sudo systemctl start ovs-vswitchd  2>/dev/null || true
sleep 1

# ── Clean up any previous Mininet state ───────────────────────────────────────
echo "[*] Cleaning up old Mininet state..."
sudo mn -c 2>/dev/null || true

# ── Start Ryu controller in background ───────────────────────────────────────
echo "[*] Starting Ryu controller (traffic_monitor.py)..."
ryu-manager traffic_monitor.py \
    --ofp-tcp-listen-port 6653 \
    --verbose \
    > ryu.log 2>&1 &
RYU_PID=$!
echo "[*] Ryu PID: $RYU_PID  (logs → ryu.log)"

sleep 3  # Give Ryu time to bind

# ── Start Mininet topology ────────────────────────────────────────────────────
echo "[*] Starting Mininet topology..."
sudo python3 topology.py

# ── Cleanup ───────────────────────────────────────────────────────────────────
echo ""
echo "[*] Stopping Ryu controller (PID $RYU_PID)..."
kill $RYU_PID 2>/dev/null || true

echo ""
echo "[✓] Done. Check traffic_log.txt for the full monitor log."
echo ""
