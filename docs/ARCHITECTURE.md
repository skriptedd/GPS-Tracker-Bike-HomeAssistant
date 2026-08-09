# Architektur

```
Companion App (Handy)          Home Assistant
──────────────────────         ─────────────────────────────────────────────
  nur Standort  ─────────►  device_tracker.<handy>
                                   │  state_changed
                                   ▼
                            coordinator.py
                              · Attribute → GpsPoint
                              · Tick alle 60 s
                                   │
                                   ▼
                            tracker.py  (Statemachine)
                              IDLE → CANDIDATE → ACTIVE → fertig
                                   │
                        ┌──────────┴──────────┐
                        ▼                     ▼
                  classify.py            geo.py
                  Fuß/Rad/Auto           Distanz, Glättung,
                                         Höhenmeter, RDP
                        │
                        ▼
                  storage.py (SQLite: config/bike_tracker.db)
                        │
        ┌───────────────┼────────────────┬──────────────┐
        ▼               ▼                ▼              ▼
   sensor.py      binary_sensor.py   http_api.py     gpx.py
   Statistik        Aufnahme?        REST für Karte  Export
                                          │
                                          ▼
                                  www/bike-tracker-card.js
```

Auf dem Handy passiert nichts außer der Standortmeldung – das war die
Kernanforderung. Jede Berechnung, jede Speicherung und die gesamte Darstellung
laufen auf dem Home Assistant.

## Warum eine eigene SQLite-Datei?

Eine Stunde Radfahren im High Accuracy Mode sind grob 700–1400 Trackpunkte.
Im Recorder wären das ebenso viele State-Rows plus Attribut-Blobs, die beim
Standard-Purge nach 10 Tagen verschwinden – Jahresstatistiken wären damit
unmöglich. `config/bike_tracker.db` ist unabhängig, klein (~150 kB pro
Fahrstunde), einfach zu sichern und lässt sich mit jedem SQLite-Tool auswerten.

## Die Statemachine

```
IDLE ──── geglättete Geschwindigkeit ≥ start_speed ────► CANDIDATE
CANDIDATE ─ hält start_duration lang durch ────────────► ACTIVE
CANDIDATE ─ Tempo fällt ───────────────────────────────► IDLE
ACTIVE ─── < stop_speed für stop_duration ─────────────► fertig
ACTIVE ─── kein Fix für stale_timeout ─────────────────► fertig
```

Der `CANDIDATE`-Puffer ist der Grund, warum keine Kilometer verloren gehen:
Sobald eine Fahrt bestätigt ist, werden die gepufferten Punkte der ersten
45 Sekunden rückwirkend in die Fahrt übernommen. Am Ende wird der Stillstand
abgeschnitten (`_trim_tail`), damit das Parken nicht als Fahrzeit zählt.

### Filterstufen vor der Statemachine

1. Fix ohne Koordinaten, mit (0,0) oder außerhalb gültiger Bereiche → weg
2. `gps_accuracy` schlechter als `max_accuracy_m` (Default 50 m) → weg
3. Zeitabstand < 0,5 s (Duplikate, out-of-order) → weg
4. Implizite Geschwindigkeit > 200 km/h → GPS-Sprung, weg
5. Geschwindigkeit: die vom Gerät gemeldete (Doppler) wird bevorzugt, weil sie
   deutlich genauer ist als das Ableiten aus Positionen; sonst Haversine/Δt
6. Gleitendes Mittel über die letzten 5 Fixes glättet Ampeln und Ausreißer

## Klassifikation

`classify.py` arbeitet auf der Geschwindigkeitsverteilung der Fahrt, nicht auf
Mittelwerten – Mittelwerte werden von Standzeiten kaputt gemacht.

| Merkmal | Bedeutung |
|---|---|
| `p85` | 85. Perzentil der Bewegungsgeschwindigkeit, das Haupt-Unterscheidungsmerkmal |
| `peak` | 95. Perzentil – ein Rad schafft 60 km/h bergab, hält sie aber nicht |
| `stop_ratio` | Anteil Standzeit – Stadtverkehr vs. Landstraße |

Regeln: `p85 ≤ 8,5` und `peak < 15` → **Fuß**. `p85 > 38` oder `peak > 65`
→ **Auto**. Alles dazwischen → **Rad**, wobei die Confidence gedämpft wird, wenn
die Fahrt schnell *und* ohne jeden Halt war (typisch Landstraßen-Auto).

Die Confidence ist der normierte Abstand zur nächsten Klassengrenze
(0,5 … 0,99). Fahrten, bei denen du unzufrieden bist, korrigierst du per
`bike_tracker.set_activity` oder direkt in der Karte – das setzt die Confidence
auf 1,0 und markiert die Fahrt als bestätigt.

## Höhenmeter

Rohe GPS-Höhe rauscht mit ±10 m. Wer alle Deltas aufsummiert, bekommt für eine
pfannkuchenflache Runde 400 Höhenmeter. Deshalb drei Stufen:

1. **Median-Filter** (Fenster 5) – entfernt einzelne Ausreißer
2. **Gleitender Mittelwert** (Fenster 5) – entfernt das verbleibende Zappeln
   (ein Median-Filter allein lässt alternierendes Rauschen durch)
3. **Hysterese** – ein Anstieg zählt erst, wenn er `elevation_threshold_m`
   (Default 3 m) über der letzten akzeptierten Referenzhöhe liegt

Das ist exakt das Verfahren, das auch Garmin/Wahoo ohne Barometer nutzen.
Ergebnis im Test: reines ±2-m-Rauschen ergibt 0 hm, ein echter 100-m-Anstieg
ergibt 85–105 hm.

<a name="tuning"></a>
## Tuning

| Symptom | Stellschraube |
|---|---|
| Fahrten starten zu spät / erste km fehlen | `Dauer über Startgeschwindigkeit` runter (z. B. 30 s) |
| Kurze Wege werden nicht erfasst | `Mindestdistanz` und `Mindestdauer` runter, oder `bike_tracker.start_trip` per Automation |
| Eine Fahrt wird in mehrere zerlegt | `Dauer unter Stoppgeschwindigkeit` hoch (z. B. 300 s) |
| Lange Standzeit am Ende zählt mit | `Stoppgeschwindigkeit` hoch (z. B. 4 km/h) |
| Distanz zu hoch, Track zappelt | `Fixes verwerfen ab Ungenauigkeit` runter (z. B. 25 m) |
| Zu viele verworfene Punkte | ebendieser Wert hoch, High Accuracy Mode prüfen |
| Autofahrten landen als Rad | Grenzen in `const.py` (`BIKE_MAX_P85`, `BIKE_MAX_PEAK`) anpassen |
| Höhenmeter zu hoch | `Rausch-Schwelle Höhenmeter` hoch (5–8 m) |

## Höhe aus Kartendaten

`elevation.py` ersetzt die GPS-Höhe optional durch Werte aus einem Höhenmodell.
Das macht Höhenmeter reproduzierbar – dieselbe Runde ergibt immer dieselbe
Zahl, weil nicht mehr das Rauschen des Handys eingeht.

```
Track (700–1400 Punkte)
   │  sample_indices()   nur alle ~25 m abfragen
   ▼                     (dichter als das 25-m-Raster des DEM, also verlustfrei)
~60 Koordinaten
   │  ElevationCache     dieselbe Straße zweimal = kein Netzverkehr
   │  Batches à 100      1 Request/s, damit der öffentliche Dienst nicht dichtmacht
   ▼
Antworten
   │  interpolate()      linear zurück auf alle Trackpunkte
   ▼
elevation_stats()        dieselbe Hysterese wie bei GPS-Höhe
```

Das Backend wird an der URL erkannt: enthält sie `open-elevation`, geht ein POST
auf `/api/v1/lookup` raus, sonst ein GET im OpenTopoData-Stil. Schlägt der
Dienst fehl, bleibt die GPS-Höhe stehen und es gibt eine Warnung im Log – eine
Fahrt geht dadurch nie verloren. Bestehende Fahrten lassen sich mit
`bike_tracker.refresh_elevation` nachrechnen.

## Segmente

Ein Segment ist ein benannter Streckenabschnitt: Startpunkt, Endpunkt und die
Länge dazwischen, herausgeschnitten aus einer bereits aufgezeichneten Fahrt
(`segment_from_track`). Jede neue Fahrt wird automatisch dagegen geprüft.

`match_segment` sucht die Stellen, an denen der Track dem Start- bzw. Endpunkt
am nächsten kommt (`_proximity_runs`, Standardradius 35 m), und paart jeden
Start mit dem ersten Ende danach. Ein Paar zählt nur, wenn die **entlang des
Tracks zurückgelegte** Distanz im Bereich der Segmentlänge liegt
(`SEGMENT_MAX_LENGTH_FACTOR`, ±35 %) – damit fällt raus, wer am Startpunkt
vorbeifährt, einen Umweg macht und später zufällig am Endpunkt landet. Von
allen gültigen Paaren gewinnt das schnellste, also die beste Runde.

Ist die Zeit besser als alles Bisherige, feuert zusätzlich zu
`bike_tracker_segment_matched` noch `bike_tracker_segment_record` – der Haken
für eine Push-Automation.

## GPX-Import

`importer.py` baut aus einer GPX-Datei eine Fahrt. Die Statemachine wird
übersprungen (die Fahrt ist ja vorbei), aber `trip_from_points` rechnet
Distanz, Bewegungszeit, Maximaltempo und Höhenmeter mit exakt derselben Logik
wie bei einer live aufgezeichneten Fahrt – die Zahlen sind also vergleichbar.

Dateien ohne `<time>` werden abgelehnt: das sind geplante Routen aus Komoot
oder BRouter, und eine Fahrt ohne Zeitstempel hätte weder Dauer noch Tempo.
Fahrten, die zeitlich mit einer bestehenden überlappen und innerhalb von zwei
Minuten starten, gelten als Duplikat und werden übersprungen.

## Was noch offen ist

* **Segmente in der UI anlegen** – aktuell nur per Service `create_segment` mit
  Punkt-Indizes aus dem Track. Komfortabler wäre, den Abschnitt direkt in der
  Karte zu ziehen.
* **Routing über mehrere Wegpunkte** – aktuell nur Start und Ziel.
* **Mehrere Räder** unterscheiden: Kilometerstand pro Rad, Wartungsintervalle.
