#!/usr/bin/env sh
# Aktualisiert Integration UND Karte auf einem Home Assistant, direkt aus dem
# GitHub-Repo. Gedacht für das Terminal-Add-on:
#
#   wget -O /tmp/update.sh https://raw.githubusercontent.com/skriptedd/GPS-Tracker-Bike-HomeAssistant/main/scripts/update_on_ha.sh
#   sh /tmp/update.sh
#
# Die Karte allein per wget zu holen reicht nicht: Fehlerbehebungen in der
# Statistik, der Höhenberechnung oder den Services stecken in
# custom_components/, nicht in der .js-Datei. Wer nur die Karte aktualisiert,
# wundert sich anschließend über unveränderte Zahlen.
#
# Angefasst werden ausschließlich:
#   <config>/custom_components/bike_tracker/
#   <config>/www/bike-tracker-card.js
# Die Fahrten-Datenbank, Automationen und alles andere bleiben unberührt.

set -eu

REPO="https://github.com/skriptedd/GPS-Tracker-Bike-HomeAssistant"
CONFIG_DIR="${1:-/config}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

                                        # GitHub leitet auf codeload um, beide
fetch() {                               # Werkzeuge folgen dem hier.
    if command -v wget >/dev/null 2>&1; then
        wget -q -O "$2" "$1"
    elif command -v curl >/dev/null 2>&1; then
        curl -fsSL -o "$2" "$1"
    else
        echo "Weder wget noch curl gefunden." >&2
        exit 1
    fi
}

echo "Ziel: $CONFIG_DIR"
echo "Lade $REPO ..."
fetch "$REPO/archive/refs/heads/main.tar.gz" "$WORK/src.tar.gz"
tar xzf "$WORK/src.tar.gz" -C "$WORK"

SRC="$WORK/GPS-Tracker-Bike-HomeAssistant-main"
[ -d "$SRC/custom_components/bike_tracker" ] || {
    echo "Archiv sieht nicht wie erwartet aus - abgebrochen." >&2
    exit 1
}

VERSION="$(sed -n 's/.*"version": *"\([^"]*\)".*/\1/p' \
    "$SRC/custom_components/bike_tracker/manifest.json" | head -1)"

mkdir -p "$CONFIG_DIR/custom_components" "$CONFIG_DIR/www"

# Alte .pyc-Dateien wegräumen: sie überleben ein Update sonst und Python
# zieht unter Umständen den alten Bytecode.
rm -rf "$CONFIG_DIR/custom_components/bike_tracker/__pycache__"
cp -r "$SRC/custom_components/bike_tracker" "$CONFIG_DIR/custom_components/"
cp "$SRC/www/bike-tracker-card.js" "$CONFIG_DIR/www/"

echo
echo "Bike Tracker $VERSION installiert:"
echo "  $CONFIG_DIR/custom_components/bike_tracker/"
echo "  $CONFIG_DIR/www/bike-tracker-card.js"
echo
echo "Jetzt Home Assistant neu starten (Entwicklerwerkzeuge -> Neu starten)."
echo "Danach im Browser Strg+F5. Bleibt die Karte alt, haengt sie im Cache:"
echo "  Einstellungen -> Dashboards -> ... -> Ressourcen"
echo "  URL auf /local/bike-tracker-card.js?v=$VERSION aendern."
