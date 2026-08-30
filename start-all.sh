#!/bin/bash
# Trading AI Experts - auto start engine + ngrok tunnel
# Auto-restarts either if it dies. Bs chalao: ./start-all.sh
cd "$(dirname "$0")"
LOG=/tmp/ta_start.log
log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$LOG"; }
is_up() { curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$1" 2>/dev/null | grep -q 200; }
start_engine() {
  is_up "http://127.0.0.1:8000/api/health" && return 0
  log "Starting engine..."
  nohup python3 run.py > /tmp/ta_engine.log 2>&1 &
  for i in $(seq 1 60); do is_up "http://127.0.0.1:8000/api/health" && { log "Engine UP"; return 0; }; sleep 2; done
  log "Engine FAILED"; return 1
}
start_tunnel() {
  curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -q '"public_url"' && return 0
  log "Starting ngrok..."
  pkill -9 ngrok 2>/dev/null; sleep 1
  nohup ngrok http 8000 --log stdout > /tmp/ngrok.log 2>&1 &
  for i in $(seq 1 20); do curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | grep -q '"public_url"' && { log "ngrok UP"; return 0; }; sleep 3; done
  log "ngrok FAILED"; return 1
}
log "=== start-all begin ==="
start_engine
start_tunnel
URL=$(curl -s http://127.0.0.1:4040/api/tunnels 2>/dev/null | python3 -c "import sys,json;ts=json.load(sys.stdin).get('tunnels',[]);print(ts[0]['public_url'] if ts else '')" 2>/dev/null)
log "PUBLIC LINK: ${URL:-https://slacks-shrimp-unlinked.ngrok-free.dev}"
while true; do start_engine; start_tunnel; sleep 30; done
