---
name: trends
description: Wertet die gesammelten Scooter-Daten aus und erklärt die erkennbaren Muster (Tageszeit, Werktag gegen Wochenende, Orte, Flottengrösse). Verwenden, wenn jemand nach Trends, Mustern oder Auffälligkeiten in den Daten fragt.
---

# Trends erklären

## Schritte

1. Neueste Daten holen: `git pull --rebase`
2. Tagesprofile berechnen:
   - `python3 analysis/daily_profile.py st_gallen --vehicle scooter`
   - `python3 analysis/daily_profile.py zurich`
   - Die Spalte `sd 9h` ist die typische Abweichung um 9 Uhr. Ist sie fast so gross wie der Durchschnitt, ist der Ort schwer vorhersagbar.
3. Flottengrösse prüfen: Summe aller Fahrzeuge um 03:00 Uhr Ortszeit pro Tag, für St. Gallen getrennt nach E-Scooter und E-Bike. Für eigene Auswertungen `analysis/load_data.py` (`iter_snapshots`) verwenden, damit Störungen herausgefiltert sind.
4. Mit dem letzten bekannten Stand vergleichen, falls er in der Unterhaltung steht.

## Bisher bekannte Muster (Stand 2026-11-26)

- An Werktagen füllen sich Büros, Hochschulen und der Bahnhof St. Gallen ab 8 Uhr, abends kehrt sich das um (Stosszeiten 8 und 18 Uhr).
- Am Wochenende gibt es dieses Muster nicht.
- Bei der HSG verteilt Dott unregelmässig um, deshalb schwanken die Werte dort stark.
- Die Flotte in St. Gallen schrumpft seit Anfang November, Zürich bleibt stabil.

## Antwort

- Auf Deutsch, Zeiten in Ortszeit, Zahlen in kleinen Tabellen.
- Klar trennen: was über viele Tage stabil ist, was neu ist und was nur eine Vermutung ist.
- Ortsnamen sind aus Koordinaten geschätzt (siehe `analysis/places.py`), darauf hinweisen, wenn sie für eine Präsentation gedacht sind.
- Am Ende sagen, was das für das Modell bedeutet.
