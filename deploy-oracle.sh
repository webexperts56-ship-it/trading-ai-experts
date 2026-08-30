#!/bin/bash
# Oracle Cloud Always Free - one-shot deploy for Trading AI Experts
# Run as root/ubuntu on the fresh Oracle VPS.
set -e

echo "=== [1/6] System packages ==="
export DEBIAN_FRONTEND=noninteractive
sudo apt-get update -y
sudo apt-get install -y python3 python3-pip python3-venv git nginx

echo "=== [2/6] Clone repo ==="
cd /opt
if [ ! -d trading-ai-experts ]; then
  sudo git clone https://github.com/webexperts56-ship-it/trading-ai-experts.git
fi
cd trading-ai-experts

echo "=== [3/6] Python venv + deps ==="
sudo python3 -m venv /opt/trading-ai-experts/venv
sudo /opt/trading-ai-experts/venv/bin/pip install --upgrade pip
sudo /opt/trading-ai-experts/venv/bin/pip install -r requirements.txt

echo "=== [4/6] Config (env) ==="
sudo tee /opt/trading-ai-experts/.env > /dev/null <<'ENVEOF'
HOST=0.0.0.0
PORT=8000
ALERTS_ENABLED=true
DESKTOP_ALERTS=false
USE_ML=true
DB_PATH=/opt/trading-ai-experts/data/signals.db
ENVEOF

echo "=== [5/6] systemd service (auto-start + always-on) ==="
sudo tee /etc/systemd/system/trading-ai.service > /dev/null <<'UNITEOF'
[Unit]
Description=Trading AI Experts real-time signal engine
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/trading-ai-experts
ExecStart=/opt/trading-ai-experts/venv/bin/python /opt/trading-ai-experts/run.py
Restart=always
RestartSec=5
EnvironmentFile=/opt/trading-ai-experts/.env
User=root

[Install]
WantedBy=multi-user.target
UNITEOF

sudo systemctl daemon-reload
sudo systemctl enable trading-ai
sudo systemctl restart trading-ai

echo "=== [6/6] Nginx reverse proxy (port 80) ==="
sudo tee /etc/nginx/sites-available/trading-ai > /dev/null <<'NGINXEOF'
server {
    listen 80 default_server;
    server_name _;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
}
NGINXEOF
sudo ln -sf /etc/nginx/sites-available/trading-ai /etc/nginx/sites-enabled/trading-ai
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
sudo ufw allow 22/tcp && sudo ufw allow 80/tcp && sudo ufw --force enable 2>/dev/null || true

echo ""
echo "=============================================="
echo " DONE. Dashboard: http://<ORACLE_PUBLIC_IP>/"
echo " Check: systemctl status trading-ai"
echo " Logs:  journalctl -u trading-ai -f"
echo "=============================================="
