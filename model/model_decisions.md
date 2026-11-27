# Modell-Entscheidungen

Kurzes Begründungs-Dokument für jede Entscheidung in `model/build_dataset.py`.
Wenn sich etwas ändert, bitte hier mit ergänzen, damit Johannes und Moritz in
`train.py` und `weather.py` wissen, warum es so ist.

## Zellen-Schwelle 10 Prozent

Eine Zelle kommt in den Trainingskatalog, wenn sie in mindestens 10 % der
gespeicherten Slots mindestens ein Fahrzeug hatte. Scooter: 475 von 722
Zellen, 1.66 Mio Zeilen. Bike: 262 von 407 Zellen, 913 k Zeilen. 5 % wäre
unnötig verrauscht (viele quasi leere Zellen), 20 % ließe zu wenig Fläche
für die Heatmap. Zellen unter der Schwelle fließen weiter in
`available_nearby` und `evening_count_nearby` ein, weil die rohen Snapshots
sie kennen.

## Zielgrößen `available` und `available_nearby`

`available` (Zelle hat mindestens ein Fahrzeug) ist die ehrliche
Prognosefrage der App. `available_nearby` (Zelle oder einer von 8 Nachbarn)
ist die nutzerfreundliche Variante: wenn der Scooter 200 m weiter steht,
ist das in der Praxis kein Fehlschlag. Das Modell soll beides lernen; die
App kann wählen, welche Zahl sie anzeigt.

## Tagesweiser Split, `SPLIT_DATE = 2026-11-21`

Train: alles vor dem 21. November 2026. Test: ab 21. November 2026.
An einem Tag teilen alle Zellen die gleiche Flottengröße, dasselbe Wetter
und dieselbe nächtliche Dott-Umverteilung. Ein zufälliger Zeilensplit würde
dem Modell erlauben, Signale aus derselben Nacht (oder sogar aus Nachbar-
Slots) zu nehmen, und würde unrealistisch gute Testwerte liefern. Mit einem
Tagessplit haben Train und Test komplett unterschiedliche Tage.

## Features Gruppe A (offline berechenbar)

Diese Spalten lassen sich aus der Zelle, der Zeit und der gespeicherten
Historie bauen. Die App kann sie ohne Live-API berechnen.

- **hour, minute_of_day, weekday, is_weekend**: aus `time` selbst. Kein Leck.
- **lecture_period**: 0 für 2026-11-02 bis 2026-11-08 (HSG-Herbstferienwoche,
  darin sind unsere ersten sieben Tage), 1 sonst. Kalenderwissen, kein Leck.
- **lat, lon**: aus `cell_center(cell_id)`, reine Funktion der Zelle.
- **rate_cell, rate_nearby**: gewichteter Mittelwert der Verfügbarkeit
  (Anteil der Slots in dieser Stunde) über alle früheren Tage gleicher
  Tagesart. In pandas: `expanding().mean().shift(1)`. Das `shift(1)`
  verhindert, dass der aktuelle Tag in seine eigene Rate einfließt.
- **recent_cell, recent_nearby**: dasselbe, aber nur über die letzten
  drei früheren Tage. `rolling(3, min_periods=1).mean().shift(1)`, so dass
  schon bei einem einzigen Vortag ein Wert kommt.
- **history_days**: Anzahl der früheren Tage, auf denen `rate_cell` beruht.
  NaN, wenn keine früheren Tage da sind (damit 0 nicht als "null Tage
  Historie" mit "keine Historie da" verwechselt wird). Macht train.py das
  Gewichten der jungen Zellen leichter.

- **temperature_c, precipitation_mm**: stündliche Werte aus Moritz'
  `model/weather.py` (Open-Meteo). Gehören in Gruppe A, weil die Prognose
  für morgen am Vorabend schon bekannt ist. **Join-Regel:** `time.dt.ceil("h")`
  verknüpft jeden Slot mit der folgenden vollen Stunde, weil Open-Meteo die
  Niederschlagsmenge bei 08:00 als Summe der Stunde 07:00 bis 08:00 liefert.
  Ein Slot um 07:10 gehört also zur Wetterzeile 08:00; ein Slot um genau
  08:00 bleibt ebenfalls bei 08:00 (ceil einer vollen Stunde ist sie selbst).
  Fehlende Wetterstunden bleiben NaN. **Caveat:** Im Training sehen wir
  tatsächliches Wetter (`get_history()`), die App nutzt dagegen die Prognose
  vom Vorabend (`get_forecast()`). Die App ist deshalb etwas ungenauer als
  die Trainingsauswertung vermuten lässt, besonders bei Regenschauern.

## Features Gruppe B (braucht Live-API)

- **evening_count_cell, evening_count_nearby, evening_fleet**: Bestand im
  spätesten gespeicherten Slot am Vortag zwischen 18:00 und 22:00 lokal
  (22:00 inklusive, 22:10 nicht). Zählt Fahrzeuge in Zelle, 3×3-Nachbar-
  schaft und gesamter St. Galler Flotte. NaN, wenn der Abend-Slot fehlt.
  Kein Leck, weil der Prognosezeitpunkt per Definition 22:00 des Vortags
  ist und der letzte 22:00-Slot damit genau zugelassen ist.

Grund für die Trennung: Wenn Moritz' Wetter-Join einmal nicht läuft oder
die Live-API ausfällt, kann die App auf Gruppe A zurückfallen, ohne die
Vorhersage ganz einzustellen.

## Baseline-Spalten (nicht Features)

- **baseline_week**: `available` derselben Zelle genau 7 Tage vorher.
  NaN, wenn der Slot vor einer Woche nicht gespeichert war.
- **baseline_week_nearby**: analog mit `available_nearby`.
- **baseline_evening**: kalibrierte Wahrscheinlichkeit
  `P(available | evening_count_cell > 0)` bzw.
  `P(available | evening_count_cell == 0)`, getrennt nach is_weekend,
  gelernt **ausschliesslich aus den Trainingstagen** (vor `SPLIT_DATE`).
  Rows ohne gespeicherten Abend-Slot bekommen NaN.

Reihenfolge der Baselines nach Stärke in der Auswertung:
1. `baseline_evening`: **die Messlatte fürs ML-Modell**. In der
   Scooter-Auswertung ab `SPLIT_DATE` schafft sie Brier 0.14 (Werktag),
   deutlich besser als `rate_cell` (0.21) oder die Konstante (0.24). Das
   Modell muss diese Marke schlagen, sonst ist der Aufwand nicht
   gerechtfertigt. `baseline_evening` ist zwei Zahlen pro Segment, also
   ein extrem einfaches "Modell"; alles was train.py mehr leistet, muss
   sich an ihr messen.
2. `rate_cell`: historische Zellenrate nach Stunde und Tagesart. Schlägt
   `baseline_week` deutlich (Brier 0.21 gegen 0.38 auf Werktagen).
3. `baseline_week`: die naive "wie vor einer Woche"-Referenz.
4. **Konstante**: Anteil `available=1` im Training, getrennt nach
   is_weekend. Druckt `evaluate()` zusätzlich, als ehrlichste Nicht-
   Zellen-Baseline. Dazu kommen der **Brier Skill Score** jeder Baseline
   gegen die Konstante, die **false-alarm**-Quote (Prognose ab 0.7, aber
   kein Fahrzeug da) und der Vergleich **mittlere Prognose vs.
   tatsächlicher Anteil** im Test.

**Was wir in der Auswertung sehen und ehrlich zugeben müssen:**
- `rate_cell` schlägt die Konstante an Werktagen nur knapp (BSS rund
  +0.09 bei Scooter). Am Wochenende reicht es nicht mehr: BSS liegt bei
  rund +0.01, praktisch gleichauf. Mit nur drei Wochenenden in der
  Historie ist die Konstante schon fast so gut wie die zelleigenen
  Mittelwerte.
- `rate_cell` **überschätzt im Test**, weil die Flotte schrumpft: die
  mittlere Werktags-Prognose liegt sichtbar über dem tatsächlichen Anteil
  (bei Scooter 0.42 gegenüber 0.36). Das ML-Modell muss diesen Trend
  mitlernen, am besten über `evening_fleet` aus Gruppe B.
- `available_nearby` ist zu rund 90 % 1 (bei Scooter), also ist jede
  konstante Prognose nahe 1 schon sehr gut. Diese Zielgröße ist daher
  **Nebenziel**, Hauptziel bleibt `available`. Nearby dient der App dazu,
  Treffer "ein Scooter steht zwei Zellen weiter" weiter als Erfolg zu
  zählen.

## Umfang: nur Scooter

Das Modell wird nur auf der Scooter-Tabelle trainiert. Grund:

- Zwischen dem 24.11. und 26.11.2026 ist die St. Galler Bike-Flotte von
  rund 140 auf etwa 24 Fahrzeuge gefallen. Zürich blieb im selben
  Zeitfenster stabil, also ist das **kein Feed-Fehler**, sondern eine
  tatsächliche Reduktion vor Ort.
- Mit nur noch rund 24 Velos ist das Signal für Zellenprognosen zu dünn;
  die historischen Raten passen nicht mehr zur aktuellen Flotte.
- Die Bike-Tabelle bleibt **baubar** (`python3 model/build_dataset.py
  --vehicle bike` funktioniert weiter), damit wir die Zahlen für die
  Präsentation ansprechen können. Trainiert wird sie nicht.

## Bekannte Grenzen

- **Kleiner Zeitraum**: Daten erst ab 2026-11-02 Abend, also nur rund drei
  Wochen und drei Wochenenden. Die Wochenend-Raten beruhen auf wenigen
  Tagen und sind entsprechend unstabil.
- **Schrumpfende Flotte**: Die absolute Fahrzeugzahl in St. Gallen nimmt
  über den Beobachtungszeitraum ab. `rate_cell` fängt das nur träge ein;
  `recent_cell` und `evening_fleet` sollen das ausgleichen.
- **HSG unregelmäßig**: Die Zellen am Campus haben historisch hohe
  Verfügbarkeiten, aber die Streuung zwischen Tagen ist groß (Vorlesungs-
  tage vs. frei). `lecture_period` codiert den Grobunterschied der ersten
  Woche, nicht einzelne Lehrveranstaltungen.
- **Vorlesungsfreie erste Woche**: 2026-11-02 bis 2026-11-08 ist in der
  HSG-Herbstferienwoche; `lecture_period = 0` ist das Flag dafür.
- **Nächtliche Umverteilung durch Dott**: Zwischen etwa 01:00 und 05:00
  verteilt Dott manuell um. `evening_count_cell` ist daher kein guter
  Prädiktor für den Vormittag; das Modell muss den Vorabend-Bestand in
  Kombination mit `rate_cell` lernen, nicht alleinstehend.

## Prognose-Zeitpunkt

Die App sagt "morgen" voraus. Als Konvention entsteht die Prognose am
**Vorabend um 22:00** lokal. Jede Spalte muss zu diesem Zeitpunkt schon
bekannt sein. Dafür steht in der Docstring jeder Feature-Spalte in
`build_dataset.py` ein kurzes "kein Leck"-Argument; der zentrale Trick
ist das `shift(1)` in den Rate-Features und die `<=22:00`-Grenze in den
Abend-Features.
