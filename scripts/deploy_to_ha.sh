#!/usr/bin/env bash
# Kopiert die Integration und die Lovelace-Karte auf den Home-Assistant-Server.
#
# Das ist der Ersatz für HACS: HACS spricht ausschließlich mit api.github.com
# und kann eine selbst gehostete GitLab-Instanz nicht erreichen (siehe README).
#
#   ./scripts/deploy_to_ha.sh root@homeassistant.local 9022
#
# Danach Home Assistant neu starten. Beim ersten Mal zusätzlich die Ressource
# /local/bike-tracker-card.js als JavaScript-Modul eintragen.

set -euo pipefail

TARGET="${1:-}"
PORT="${2:-22}"
CONFIG_DIR="${3:-/config}"

if [[ -z "$TARGET" ]]; then
    echo "Aufruf: $0 <user@host> [ssh-port] [config-verzeichnis]" >&2
    echo "Beispiel: $0 root@homeassistant.local 9022" >&2
    exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "Ziel : $TARGET:$CONFIG_DIR (SSH-Port $PORT)"
echo "Quelle: $REPO_ROOT"
echo

# Verzeichnisse anlegen, falls sie noch nicht existieren.
ssh -p "$PORT" "$TARGET" "mkdir -p $CONFIG_DIR/custom_components $CONFIG_DIR/www"

# __pycache__ nicht mitschleppen - alte .pyc-Dateien können nach einem Update
# eine Version vortäuschen, die gar nicht mehr da ist.
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
cp -r custom_components/bike_tracker "$TMP_DIR/"
find "$TMP_DIR" -name __pycache__ -type d -prune -exec rm -rf {} +

scp -P "$PORT" -r "$TMP_DIR/bike_tracker" "$TARGET:$CONFIG_DIR/custom_components/"
scp -P "$PORT" www/bike-tracker-card.js "$TARGET:$CONFIG_DIR/www/"

VERSION="$(grep -o '"version": *"[^"]*"' custom_components/bike_tracker/manifest.json | cut -d'"' -f4)"
echo
echo "Bike Tracker $VERSION kopiert."
echo "Jetzt Home Assistant neu starten: Entwicklerwerkzeuge -> Neu starten."
