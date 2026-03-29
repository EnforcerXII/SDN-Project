#!/bin/bash
# run.sh — Launch the SDN Traffic Monitor (POX version)
# Usage: bash run.sh
# Requires: POX (cloned), mininet, sudo

set -e

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║    SDN Traffic Monitor — UE24CS252B      ║"
echo "║    Controller: POX (OpenFlow 1.0)        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Locate POX ────────────────────────────────────────────────────────────────
POX_DIR=""
for candidate in "$HOME/pox" "./pox" "../pox" "/opt/pox"; do
    if [ -f "$candidate/pox.py" ]; then
        POX_DIR="$candidate"
        break
    fi
done

if [ -z "$POX_DIR" ]; then
    echo "[ERROR] POX not found. Clone it first:"
    echo "        git clone https://github.com/noxrepo/pox ~/pox"
    exit 1
fi

echo "[*] Found POX at: $POX_DIR"

# ── Check mininet ─────────────────────────────────────────────────────────────
if ! command -v mn &>/dev/null; then
    echo "[ERROR] Mininet not found. Install: sudo apt install mininet"
    exit 1
fi

# ── Copy controller into POX ext/ ─────────────────────────────────────────────
echo "[*] Installing traffic_monitor.py into POX ext/..."
cp traffic_monitor.py "$POX_DIR/ext/traffic_monitor.py"

# ── Clean up any previous Mininet state ───────────────────────────────────────
echo "[*] Cleaning up old Mininet state..."
sudo mn -c 2>/dev/null || true

# ── Start POX controller in background ───────────────────────────────────────
echo "[*] Starting POX controller..."
cd "$POX_DIR"
python3 pox.py log.level --DEBUG traffic_monitor > /tmp/pox.log 2>&1 &
POX_PID=$!
cd - > /dev/null
echo "[*] POX PID: $POX_PID  (logs → /tmp/pox.log)"

sleep 4  # Give POX time to bind on :6633

# ── Start Mininet ─────────────────────────────────────────────────────────────
echo "[*] Starting Mininet topology..."
sudo python3 topology.py

# ── Cleanup ───────────────────────────────────────────────────────────────────
echo ""
echo "[*] Stopping POX (PID $POX_PID)..."
kill $POX_PID 2>/dev/null || true

echo ""
echo "[✓] Done. Check traffic_log.txt for the full monitor log."
echo ""
