# Changelog

## 0.2.0

Arbeitet die vier offenen Punkte aus 0.1.0 ab.

### Höhe aus Kartendaten

* Neue Höhenquelle **dem**: fragt ein Höhenmodell ab (OpenTopoData oder
  Open-Elevation, Backend wird an der URL erkannt) statt die GPS-Höhe zu nutzen
* Sampling alle ~25 m, Batches à 100 Koordinaten, 1 Request/s, Cache über
  gerundete Koordinaten – dieselbe Straße kostet beim zweiten Mal nichts
* Neue Option **URL des Höhendienstes**
* Neuer Service `refresh_elevation`, rechnet bestehende Fahrten nach
* Fällt der Dienst aus, bleibt die GPS-Höhe stehen – eine Fahrt geht nie verloren

### GPX-Import

* Neuer Service `import_gpx` für eine Datei oder einen ganzen Ordner
* Namespace-toleranter Parser (GPX 1.0 und 1.1), mehrere `<trk>` und `<trkseg>`
* Dateien ohne Zeitstempel (geplante Routen) werden mit klarer Begründung
  abgelehnt statt als Null-Sekunden-Fahrt gespeichert
* Duplikaterkennung über Zeitüberlappung
* `trip_from_points()` rechnet importierte Fahrten mit derselben Logik wie
  live aufgezeichnete

### Segmente & Bestzeiten

* Neue Tabellen `segments` und `segment_efforts` (Schema-Version 2, migriert
  beim Start von selbst)
* `match_segment()` mit Proximity-Erkennung und Längen-Plausibilitätsprüfung,
  von mehreren Runden gewinnt die schnellste
* Services `create_segment`, `delete_segment`, `rescan_segments`
* Events `segment_matched` und `segment_record` (neue Bestzeit)
* REST: `GET /segments`, `GET`/`DELETE /segments/{id}`

### Routing-UI

* Panel „Route planen" in der Lovelace-Karte: Start/Ziel (Koordinaten oder
  Zonennamen), Profil, optionaler Push ans Handy
* Route wird gestrichelt über den Track gelegt
* Neuer Endpunkt `POST /api/bike_tracker/route`
* Neue Karten-Optionen `show_route`, `show_segments`, `notify_service`

### Sonstiges

* `scripts/replay_track.py` simuliert eine Fahrt über die REST-API – die
  komplette Erkennung lässt sich damit ohne Fahrrad testen
* Neue Doku `docs/TESTING.md`
* 83 statt 41 Tests, weiterhin ohne Home-Assistant-Installation lauffähig

## 0.1.0 – erste Version

* Automatische Fahrterkennung aus dem `device_tracker` der Companion App
  (Statemachine mit Kandidaten-Puffer, Stillstands-Trimmen, Sprung- und
  Genauigkeitsfilter)
* Klassifikation Fuß / Rad / Auto anhand der Geschwindigkeitsverteilung
* Höhenmeter aus GPS-Höhe, dreistufig entrauscht
* SQLite-Persistenz in `config/bike_tracker.db` inkl. Trackpunkten
* 28 Statistik-Sensoren (heute/Woche/Monat/Jahr/gesamt) plus Live-Sensoren
* Config Flow und Options Flow, Übersetzungen DE/EN
* Services: `start_trip`, `stop_trip`, `discard_trip`, `set_activity`,
  `delete_trip`, `export_gpx`, `plan_route`, `purge`
* Events: `trip_started`, `trip_finished`, `trip_discarded`, `route_planned`
* REST-API für Fahrten, Tracks, Statistik, GPX und laufende Fahrt
* Lovelace-Karte mit Leaflet-Track, Höhenprofil, Balkendiagramm und
  Aktivitäts-Korrektur
* GPX-1.1-Export
* Routing-Grundgerüst mit OSRM- und BRouter-Backend
* 41 Unit-Tests gegen synthetische GPS-Tracks, ohne HA-Installation lauffähig
