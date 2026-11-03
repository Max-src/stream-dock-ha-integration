#!/bin/bash
# Starts the throwaway Home Assistant and keeps this WSL session open, because
# WSL stops the distro (and Home Assistant with it) once no Windows session is
# attached. Run it in the background from Windows: wsl -d Ubuntu -- bash e2e/keep-ha-up.sh
cd "$(dirname "$0")/.." || exit 1
bash e2e/start-ha.sh
while kill -0 "$(cat "$HOME/ha-e2e/hass.pid")" 2>/dev/null; do
    sleep 30
done
echo "Home Assistant stopped"
