# ScootCast

Sagt voraus, ob morgen früh zu einer bestimmten Uhrzeit ein E-Scooter oder Leihvelo in deiner Nähe steht. Gruppenprojekt im Kurs «Fundamentals and Methods of Computer Science» an der HSG.

## Datensammlung

Die API von sharedmobility.ch zeigt nur den aktuellen Stand. Deshalb speichert GitHub Actions ([collect.yml](.github/workflows/collect.yml)) alle 10 Minuten einen Schnappschuss ins Repository.

| Stadt | Ablage | Intervall | Detail |
|---|---|---|---|
| St. Gallen | `data/st_gallen/<Datum>.csv` | 10 Min. | pro Zelle, Anbieter und Fahrzeugtyp |
| Zürich (Absicherung) | `data/zurich/<Datum>.csv` | 30 Min. | nur pro Zelle (`all` in beiden Spalten) |

Bricht die grosse Datei ab oder enthält sie keine Fahrzeuge, holt der Scraper St. Gallen stattdessen über die Karten-Schnittstelle von sharedmobility.ch (`api.sharedmobility.ch/v1/sharedmobility/identify`). Zürich fehlt dann für diesen Zeitpunkt. Die Fahrzeugtypen von Dott werden dabei in die Namen der grossen Datei übersetzt. Andere Anbieter behalten den Namen der Karte, zum Beispiel `carvelo2go:E-CargoBike`.

### Datenformat

```text
timestamp,cell_id,provider_id,vehicle_type_id,count
2026-11-02T20:50:00Z,26377_3500,dott_st-gallen,dott_st-gallen:dott_scooter,1
```

- `timestamp`: Zeitpunkt in **UTC**, abgerundet auf das Intervall. Für Uhrzeit und Wochentag zuerst nach `Europe/Zurich` umrechnen. Dateien sind ebenfalls nach UTC-Tag benannt.
- `cell_id`: Zelle im 200-m-Raster, Zeile und Spalte. `collect.cell_center()` liefert den Mittelpunkt für die Karte.
- `count`: Anzahl mietbarer Fahrzeuge. Gesperrte und reservierte Fahrzeuge werden nicht gezählt.
- Zellen ohne Fahrzeug haben **keine Zeile**. Eine fehlende Zelle bedeutet also «0 Fahrzeuge», wenn der Zeitpunkt selbst in den Daten vorkommt.

### Befehle

Keine zusätzlichen Pakete nötig, nur Python 3.11 oder neuer.

```bash
python3 collector/collect.py
```

```bash
python3 collector/check_gaps.py
```

```bash
python3 -m unittest discover tests
```

Der Bot committet laufend neue Daten. Deshalb vor dem Pushen immer zuerst `git pull --rebase` ausführen.

## Quellen

- Fahrzeugdaten: Bundesamt für Energie (BFE), [sharedmobility.ch](https://sharedmobility.ch/gbfs.json), via opendata.swiss

## KI-Nutzung

Die Kursregeln verlangen, generierten Code in der Quelle zu zitieren. Jede generierte Datei trägt deshalb oben einen Hinweis `AI citation`.
