---
name: abgabe-check
description: Prüft den Stand von ScootCast gegen die 8 Bewertungskriterien und die Abgaberegeln des FCS-Kurses (Abgabe 10.12.2026, 23:59). Verwenden, wenn jemand wissen will, was für die Abgabe noch fehlt oder ob das Projekt bereit ist.
disable-model-invocation: true
---

# Abgabe prüfen

Quelle der Regeln: Folien 4, 8, 9 und 10 von `FCS-BWL-GroupProject.pdf` (Canvas). Die Kriterien stehen unten, das PDF ist nicht nötig. Jedes Kriterium gibt 0 bis 3 Punkte (0 fehlt, 1 einfach, 2 gut, 3 weit über Kursniveau).

## Die 8 Kriterien und wie man sie prüft

| Nr. | Kriterium | Prüfen |
|---|---|---|
| 1 | Problem klar beschrieben | README und App-Startseite nennen das Problem |
| 2 | Daten über API oder Datenbank | Collector und App-Services lesen die Daten |
| 3 | Daten werden visualisiert | `app.py` und `components/` zeigen Karte oder Diagramme |
| 4 | Nutzer kann interagieren | Eingaben wie Ort, Uhrzeit, Wochentag in der App |
| 5 | Eigenes Machine-Learning-Modell | Modell wird mit unseren Daten trainiert und in der App verwendet |
| 6 | Code gut kommentiert | jede Funktion hat Docstring, schwierige Stellen haben Kommentare |
| 7 | Beiträge und KI-Nutzung dokumentiert | Beitragsmatrix vorhanden, KI-Nutzung beschrieben |
| 8 | Video, 4 Minuten, Stimme nicht generiert | nur erinnern, kann nicht im Code geprüft werden |

## Weitere Pflichten

- Jede `.py`-Datei mit KI-Code hat oben einen Hinweis `AI citation` mit Tool, Modell und Datum. Prüfen mit: `grep -L "AI citation" $(git ls-files "*.py")`
- Die App startet: `pip install -r requirements.txt` und `streamlit run app.py`. Fehlende Pakete in `requirements.txt` melden.
- README erklärt, wie man die App startet.
- Tests laufen: `python3 -m unittest discover tests`
- Erklärung zur Eigenständigkeit (eine pro Gruppe) ist geplant.
- Abgabe direkt auf Canvas hochladen, ein Link auf GitHub reicht nicht.

## Antwort

- Tabelle mit allen 8 Kriterien: Stand, geschätzte Punkte, was für den nächsten Punkt fehlt.
- Danach die weiteren Pflichten als Liste mit erfüllt oder offen.
- Zum Schluss die 3 wichtigsten nächsten Schritte, gemessen an Punkten pro Aufwand und an den Tagen bis zur Abgabe.
- Nichts automatisch ändern. Nur berichten.
