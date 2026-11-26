# ScootCast

Streamlit-App für die FCS-Gruppenarbeit an der HSG (5 Personen). Sie sagt voraus, ob zu einer bestimmten Zeit an einem Ort in St. Gallen ein E-Scooter oder Leihvelo verfügbar ist. Abgabe am 10.12.2026 um 23:59 auf Canvas, Video-Präsentation mit Fragerunde am 11.12.2026. Der Projektvorschlag und die Kursvorgaben liegen bei Erik in `~/OneDrive/Unisg/HeSe 2026/Computer Science/group project/`.

## Regeln

- Antworte auf Deutsch. Code, Kommentare und Commit-Messages sind auf Englisch.
- Pflicht laut Kursregeln: Jede Datei mit KI-generiertem Code bekommt oben einen Hinweis `AI citation` mit Tool, Modell und Datum. Ein Hook in `.claude/settings.json` erinnert daran.
- Pflicht laut Bewertung: Der Code ist gut kommentiert. Jede Funktion hat einen Docstring.
- Nur echte, selbst gesammelte Daten verwenden, keine synthetischen Trainingsdaten.
- `data/` wird vom Bot geschrieben. Dort nichts von Hand ändern, auch nicht zum Bereinigen. Bekannte Störungen stehen stattdessen in `analysis/outages.csv`.
- Zeitstempel in `data/` sind UTC. Für Modell und App nach `Europe/Zurich` umrechnen (`analysis/load_data.py` macht das).
- Keine Geheimnisse ins Repo, vor allem nicht den GitHub-Token von cron-job.org.
- Fremden Code von Teammitgliedern nur nach Rückfrage umbauen.

## Aufbau

| Ordner | Inhalt |
|---|---|
| `collector/` | Scraper, der alle 5 Minuten über GitHub Actions läuft, und `check_gaps.py` |
| `data/` | gesammelte Schnappschüsse, eine CSV pro Stadt und UTC-Tag |
| `analysis/` | Daten laden (`load_data.py`), Orte (`places.py`), Tagesprofile (`daily_profile.py`), Störungsliste (`outages.csv`) |
| `app.py`, `components/`, `services/`, `models/` | Streamlit-App |
| `tests/` | Tests mit `unittest` |
| `.claude/` | gemeinsame Claude-Code-Einstellungen, Hook und Skills |

## Befehle

```bash
python3 -m unittest discover tests
python3 collector/check_gaps.py
python3 analysis/daily_profile.py st_gallen --vehicle scooter
pip install -r requirements.txt
streamlit run app.py
```

## Daten

- Spalten: `timestamp,cell_id,provider_id,vehicle_type_id,count`. Zellen sind 200 m gross, `collect.cell_center()` gibt den Mittelpunkt.
- Eine fehlende Zelle heisst 0 Fahrzeuge, wenn der Zeitpunkt selbst gespeichert ist.
- St. Gallen alle 10 Minuten mit Anbieter und Fahrzeugtyp, Zürich alle 30 Minuten nur pro Zelle (`all`).
- Für Analysen und Training immer `analysis/load_data.py` verwenden, damit Störungen herausgefiltert sind.
- Erkenntnisse bisher: starkes Pendlermuster an Werktagen, keines am Wochenende, HSG schwer vorhersagbar, Flotte in St. Gallen schrumpft. Das Modell braucht Uhrzeit, Werktag oder Wochenende, Zelle und die aktuelle Flottengrösse.

## Zusammenarbeit

- Vor jedem Push `git pull --rebase`, weil der Bot laufend Daten committet.
- Kleine Commits mit klarer Message. Wer was beigetragen hat, muss am Ende in einer Beitragsmatrix stehen.

## Skills

- `/sammlung`: prüft, ob die Datensammlung läuft
- `/trends`: wertet die Daten aus und erklärt die Muster
- `/abgabe-check`: prüft den Stand gegen die 8 Bewertungskriterien
