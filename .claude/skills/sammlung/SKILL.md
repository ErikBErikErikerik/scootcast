---
name: sammlung
description: Prüft, ob die automatische Datensammlung von ScootCast läuft. Verwenden, wenn jemand fragt, ob alles klappt, ob Daten fehlen, ob der Scraper oder die GitHub-Läufe funktionieren.
---

# Datensammlung prüfen

Ziel: in wenigen Sätzen sagen, ob die Sammlung läuft, was seit der letzten Prüfung schiefging und ob jemand etwas tun muss.

## Schritte

1. Neueste Daten holen: `git pull --rebase`
2. Lücken prüfen: `python3 collector/check_gaps.py`
   - Alte Lücken (vor dem 2026-11-17) sind bekannt und müssen nicht erwähnt werden.
3. GitHub-Läufe prüfen:
   - `gh run list --workflow collect.yml --limit 300 --json conclusion,createdAt,databaseId`
   - Für jeden Lauf mit `failure` oder `startup_failure` die Ursache lesen: `gh run view <id> --log | grep -E "Feed failed|no vehicles|st_gallen:|zurich:|error|403|CONFLICT"`
   - `gh` kann hängen. Den Befehl dann im Hintergrund laufen lassen statt mehrmals neu zu starten.
4. Auffällige Einbrüche suchen: Zeitpunkte, an denen in St. Gallen weniger als 60 % der üblichen E-Scooter oder in Zürich mehr als 1000 Fahrzeuge weniger als sonst gezählt wurden. Bei einem Einbruch in beiden Städten zur gleichen Zeit ist es wahrscheinlich eine Störung beim Anbieter.
5. Grösse der Daten: `du -sh data`

## Bekannte Ursachen und was sie bedeuten

| Meldung | Ursache | Handlung |
|---|---|---|
| `Feed failed (IncompleteRead ...)` | sharedmobility.ch bricht den Download ab | keine, St. Gallen kommt über die Ausweichquelle, Zürich fehlt kurz |
| `feed lists no vehicles` | Feed nachts leer | keine, Ausweichquelle springt ein |
| `startup_failure` oder Lauf ohne Jobs | Störung bei GitHub | keine |
| `403` beim Push | GitHub lehnt kurz ab | keine, der nächste Lauf speichert den Slot |
| `CONFLICT` beim Rebase | zwei Läufe gleichzeitig | keine, solange `check_gaps.py` keine Lücke zeigt |
| viele Läufe hintereinander ohne Erfolg | echtes Problem | melden, Logs lesen, Ursache suchen |

## Antwort

- Auf Deutsch, Zeiten in Schweizer Ortszeit (UTC plus 1 Stunde im Winter).
- Zuerst das Urteil (läuft oder läuft nicht), dann Abdeckung pro Stadt, neue Lücken mit Ursache, Auffälligkeiten.
- Neue Störungen, die das Training verfälschen würden, als Vorschlag für `analysis/outages.csv` nennen. Nur nach Zustimmung eintragen.
- Nichts in `data/` ändern.
