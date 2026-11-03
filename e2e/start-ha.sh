#!/bin/bash
# Starts a throwaway Home Assistant in WSL for end-to-end tests, on port 8124,
# with the integration from this repo linked in. Everything lives in ~/ha-e2e,
# so the person's real Home Assistant is never involved.
#   bash e2e/start-ha.sh        start (or restart) it
#   bash e2e/start-ha.sh stop   stop it
set -e
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="${HA_PY:-$HOME/venvs/stream-dock-ha/bin/python}"
ROOT="$HOME/ha-e2e"
CONF="$ROOT/config"

stop() {
    if [ -f "$ROOT/hass.pid" ]; then
        kill "$(cat "$ROOT/hass.pid")" 2>/dev/null || true
        rm -f "$ROOT/hass.pid"
        sleep 2
    fi
}

if [ "$1" = "stop" ]; then
    stop
    exit 0
fi
stop

mkdir -p "$CONF/custom_components"
ln -sfn "$REPO/custom_components/stream_dock_ha" "$CONF/custom_components/stream_dock_ha"
cp "$REPO/e2e/configuration.yaml" "$CONF/configuration.yaml"
# Home Assistant 2026 keeps the HTTP port in .storage/http and only takes the
# YAML one after it's confirmed in the UI, so it falls back to 8123 on a restart.
# Set 8124 there directly.
"$PY" - "$CONF/.storage/http" <<'EOF'
import json, pathlib, sys
path = pathlib.Path(sys.argv[1])
if path.exists():
    data = json.loads(path.read_text())
    data["data"]["stable"]["server_port"] = 8124
    data["data"]["pending"] = None
    path.write_text(json.dumps(data, indent=2))
EOF
# Any copy started some other way (by hand, or by an older run) goes too.
pkill -f "homeassistant -c $CONF" 2>/dev/null || true
sleep 1

nohup "$PY" -m homeassistant -c "$CONF" --skip-pip > "$ROOT/hass.log" 2>&1 &
echo $! > "$ROOT/hass.pid"

for _ in $(seq 1 300); do
    if curl -s -o /dev/null "http://127.0.0.1:8124/manifest.json"; then
        echo "Home Assistant is up on http://127.0.0.1:8124"
        exit 0
    fi
    sleep 1
done
echo "Home Assistant didn't start; see $ROOT/hass.log"
tail -40 "$ROOT/hass.log"
exit 1
