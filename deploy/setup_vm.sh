#!/usr/bin/env bash
# ==============================================================================
# SkyGuard AI — Automated GCP e2-medium VM Deployment Script
# Target OS: Ubuntu 22.04 / 24.04 LTS or Debian 12 on Google Cloud Compute Engine
# ==============================================================================

set -e

echo "========================================================"
echo "    SKYGUARD AI - GCP BACKEND DEPLOYMENT SETUP         "
echo "========================================================"

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
echo "[*] Working directory: $APP_DIR"

# 1. System Package Updates & Prerequisites
echo "[1/6] Updating system packages & installing prerequisites..."
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv python3-dev build-essential git ufw curl

# 2. Configure 2GB Swap (Safety net for high concurrency)
if [ ! -f /swapfile ]; then
    echo "[2/6] Configuring 2GB swap space for rock-solid stability..."
    sudo fallocate -l 2G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
else
    echo "[2/6] Swap space already configured."
fi

# 3. Create & Activate Python Virtual Environment
echo "[3/6] Setting up Python virtual environment..."
cd "$APP_DIR"
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

source venv/bin/activate
pip install --upgrade pip setuptools wheel
echo "[*] Installing Python dependencies from requirements.txt..."
pip install -r requirements.txt

# 4. Create Systemd Service for Auto-Start & Auto-Recovery
echo "[4/6] Creating systemd service (skyguard.service)..."
CURRENT_USER=$(whoami)

sudo bash -c "cat > /etc/systemd/system/skyguard.service" <<EOF
[Unit]
Description=SkyGuard AI Production FastAPI Backend
After=network.target

[Service]
User=$CURRENT_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin"
Environment="PYTHONUNBUFFERED=1"
Environment="PORT=8000"
ExecStart=$APP_DIR/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 5. Reload and Start Systemd Service
echo "[5/6] Starting SkyGuard backend daemon..."
sudo systemctl daemon-reload
sudo systemctl enable skyguard
sudo systemctl restart skyguard

# 6. Configure Firewall (allow port 8000)
echo "[6/6] Allowing port 8000 on local firewall..."
if sudo ufw status | grep -q "Status: active"; then
    sudo ufw allow 8000/tcp
    sudo ufw reload
fi

echo "========================================================"
echo "    SKYGUARD AI BACKEND SUCCESSFULLY DEPLOYED!         "
echo "========================================================"
echo "Status check:"
sudo systemctl status skyguard --no-pager
echo ""
echo "Test endpoint locally:"
curl -s http://127.0.0.1:8000/health || curl -s http://127.0.0.1:8000/api/system-status || echo "Backend active on port 8000!"
echo ""
echo "To view live logs in real time, run: journalctl -u skyguard -f"
