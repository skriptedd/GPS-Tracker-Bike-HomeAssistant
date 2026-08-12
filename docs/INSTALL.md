# Installation

> Benötigt Home Assistant **2024.11** oder neuer.

## Weg A: HACS (empfohlen)

1. HACS öffnen → **⋮ → Benutzerdefinierte Repositories**
2. URL dieses Repos eintragen, Kategorie **Integration**
3. „Bike Tracker" herunterladen, Home Assistant neu starten

> **Integration, nicht Add-on.** Trag das Repo **nicht** unter
> *Einstellungen → Add-ons → Store → ⋮ → Repositories* ein – dort kommt
> „is not a valid add-on repository". Add-ons sind eigene Docker-Container und
> brauchen `repository.yaml` plus `config.yaml` und `Dockerfile`; dieses Repo
> enthält ein Custom Component unter `custom_components/`. Das gehört
> ausschließlich in HACS.

Zwei Dinge, die HACS nicht kann und die immer wieder für Verwirrung sorgen:

* **Nur GitHub.** HACS klont nicht, es spricht ausschließlich mit
  `api.github.com` (einzige Abhängigkeit: `aiogithubapi`). Selbst gehostete
  GitLab-, Gitea- oder Codeberg-Instanzen sind prinzipiell nicht erreichbar.
* **Nur öffentlich.** Laut FAQ gilt: *„HACS can only get publicly available
  information"* – private GitHub-Repos funktionieren ausdrücklich nicht.

Trifft eines davon zu, nimm Weg B.

## Weg B: Kopieren

Ein Befehl, keine Tokens, keine Zertifikatsprobleme – und der einzige Weg, wenn
das Repo nicht öffentlich auf GitHub liegt.

```bash
./scripts/deploy_to_ha.sh root@homeassistant.local 22 /pfad/zum/config
```

Das Skript legt die Zielverzeichnisse an, wirft `__pycache__` raus und kopiert
Integration **und** Karte. Der dritte Parameter ist das Verzeichnis, das dein
Home Assistant als `/config` sieht – bei einer Docker-Installation ist das ein
Host-Pfad, **nicht** `/config`. Welcher, verrät dir:

```bash
docker inspect -f '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}' homeassistant
```

Das offizielle `git_pull`-Add-on wäre theoretisch auch eine Option – es kann
jedes Git-Hosting und hat Felder für Benutzer und Passwort. Es klont aber nach
`/config` und ist dafür gedacht, die **gesamte** Konfiguration aus Git zu
verwalten; mit `git_command: reset` läuft dort ein `git reset --hard`. Für ein
einzelnes Custom Component ist das zu scharf, und es würde zusätzlich `docs/`,
`tests/` und `README.md` nach `/config` kippen.

Die Einzelheiten von Hand:

## 1. Integration kopieren

Ziel ist immer `<config>/custom_components/bike_tracker/`. Wo `<config>` liegt,
hängt von deiner Installationsart ab:

| Installationsart | Pfad |
|---|---|
| Home Assistant OS / Supervised | `/config` (per Samba, SSH-Addon oder Studio Code Server) |
| Home Assistant Container / Docker | das Volume, das du auf `/config` gemountet hast, z. B. `/opt/homeassistant/config` |
| Home Assistant Core (venv) | `~/.homeassistant` |

```bash
# Beispiel Docker: Container heißt "homeassistant"
docker cp custom_components/bike_tracker homeassistant:/config/custom_components/
docker restart homeassistant
```

```bash
# Beispiel HA OS mit aktiviertem SSH-Addon
scp -P 22222 -r custom_components/bike_tracker root@homeassistant.local:/config/custom_components/
```

Danach Home Assistant neu starten (**Entwicklerwerkzeuge → Neu starten**).

> **Bei Docker-Installationen der häufigste Fehler:** Du verbindest dich per SSH
> auf den *Host* und kopierst nach `/config`. Damit legst du ein neues, leeres
> Verzeichnis auf dem Host an – ohne Fehlermeldung, und Home Assistant sieht
> davon nie etwas. Ziel ist immer das Volume, das der Container als `/config`
> gemountet bekommt.

## 2. Lovelace-Karte registrieren

```bash
cp www/bike-tracker-card.js <config>/www/
```

**Einstellungen → Dashboards → ⋮ → Ressourcen → + Ressource hinzufügen**

* URL: `/local/bike-tracker-card.js`
* Typ: JavaScript-Modul

Dann Browser-Cache leeren (Strg+F5).

### Ohne Internet

Die Karte lädt Leaflet standardmäßig von unpkg.com. Wenn dein HA keinen
Internetzugang hat, lege `leaflet.js` und `leaflet.css` in `<config>/www/` ab
und konfiguriere:

```yaml
type: custom:bike-tracker-card
leaflet_url: /local/leaflet.js
leaflet_css: /local/leaflet.css
tile_url: http://homeassistant.local:8080/tile/{z}/{x}/{y}.png
```

## 3. Companion App vorbereiten

In der Home-Assistant-App auf dem Handy:

1. **Einstellungen → Companion App → Sensoren verwalten**
2. **Hintergrund-Standort** aktivieren
3. **High Accuracy Mode** einschalten (Android: „Hohe Genauigkeit erzwingen";
   iOS liefert im Hintergrund automatisch dichte Updates, wenn Standort auf
   „Immer" steht)
4. Akku-Optimierung für die App deaktivieren, sonst friert Android den
   Standortdienst ein

Der High Accuracy Mode kostet spürbar Akku. Ein guter Kompromiss ist, ihn per
Automation nur einzuschalten, wenn du nicht zu Hause bist:

```yaml
automation:
  - alias: High Accuracy nur unterwegs
    trigger:
      - platform: state
        entity_id: person.timo
    action:
      - service: >-
          {{ 'switch.turn_off' if is_state('person.timo','home') else 'switch.turn_on' }}
        target:
          entity_id: switch.pixel_8_high_accuracy_mode
```

## 4. Integration einrichten

**Einstellungen → Geräte & Dienste → + Integration hinzufügen → Bike Tracker**

Wähle den `device_tracker`, der Latitude/Longitude liefert – typischerweise
`device_tracker.<handyname>`. `person.*` funktioniert auch, ist aber ungenauer,
weil es zwischen mehreren Quellen umschaltet.

## 5. Höhenquelle wählen (optional)

**Integration → Konfigurieren → Höhenquelle**

| Wert | Verhalten |
|---|---|
| GPS-Höhe | Standard. Die Höhe des Handys, dreistufig entrauscht. Kostet nichts, rauscht aber |
| Kartendaten | Fragt ein Höhenmodell ab. Reproduzierbar – dieselbe Runde ergibt immer dieselben Höhenmeter |
| keine | Keine Höhenmeter |

Bei *Kartendaten* steht darunter die **URL des Höhendienstes**. Voreingestellt
ist der öffentliche OpenTopoData mit EU-DEM 25 m – der erlaubt 1000 Aufrufe pro
Tag, was für ein paar Fahrten reicht. Wer mehr braucht (oder den Altbestand per
`bike_tracker.refresh_elevation` neu rechnen will), hostet ihn selbst:

```bash
docker run -d --name opentopodata -p 5000:5000 \
  -v /opt/opentopodata/data:/app/data giswqs/opentopodata
# URL in den Optionen: http://homeassistant.local:5000/v1/eudem25m
```

Ist der Dienst nicht erreichbar, bleibt die GPS-Höhe stehen und es landet eine
Warnung im Log – die Fahrt geht nicht verloren.

## 6. Prüfen, ob Daten ankommen

**Entwicklerwerkzeuge → Zustände** → deinen `device_tracker` suchen. Die
Attribute müssen `latitude`, `longitude` und idealerweise `gps_accuracy` und
`altitude` enthalten. Fehlt `altitude`, gibt es keine Höhenmeter – dann liefert
dein Gerät keine Höhe und du kannst „Höhenquelle" in den Optionen auf *keine*
stellen.

Während einer Testfahrt:

* `binary_sensor.bike_tracker_zeichnet_auf` muss nach ~45 s Fahrt auf **an** gehen
* `sensor.bike_tracker_aktuelle_geschwindigkeit` muss plausible Werte zeigen
* Im Log (`custom_components.bike_tracker` auf `debug`) siehst du jede erkannte
  und jede verworfene Fahrt:

```yaml
logger:
  default: warning
  logs:
    custom_components.bike_tracker: debug
```

Wie du das Ganze ohne Fahrrad durchtestest, steht in [TESTING.md](TESTING.md).

## Deinstallieren

Integration löschen, Ordner `custom_components/bike_tracker` entfernen. Die
Fahrten bleiben in `<config>/bike_tracker.db` – diese Datei musst du bei Bedarf
selbst löschen.
