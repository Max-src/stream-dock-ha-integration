#!/bin/bash
# Starts the throwaway Home Assistant and keeps this WSL session open for good,
# because WSL stops the distro (and Home Assistant with it) once no Windows
# session is attached. Run it in the background from Windows:
#   wsl -d Ubuntu -- bash e2e/keep-ha-up.sh
# Restarting Home Assistant with start-ha.sh meanwhile is fine.
cd "$(dirname "$0")/.." || exit 1
bash e2e/start-ha.sh
exec sleep infinity
