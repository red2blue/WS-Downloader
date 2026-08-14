# Changelog

Alle nennenswerten Aenderungen an `WS Downloader` werden hier dokumentiert.

## v0.8 - 2026-05-19

### Hinzugefuegt

- Versionsanzeige unten rechts in der Hauptansicht
- `README.md` und `README_SHORT.md` im `dist`-Ordner
- Automatische SteamCMD-Pruefung und Selbstaktualisierung ueber `steamcmd +quit`
- Button zur automatischen SteamCMD-Installation, wenn SteamCMD nicht gefunden wird
- Mod-Tabelle mit Spalte fuer den effektiven lokalen Zielordner
- Optionaler lokaler Zielordner pro Mod
- Uebernahme eines Dateinamens als Zielordnername ohne Dateiendung
- Startordner fuer die Dateiauswahl im Mod-Ordner bzw. Mods-Verzeichnis des aktuellen Spiels
- Auswahl-Checkboxen mit `☐` und `☑`
- `+/-`-Button zum Auswaehlen oder Abwaehlen aller sichtbaren Mods
- Sichtbarer Modus-Hinweis im Mod-Dialog fuer Workshop-ID oder benutzerdefinierten Zielordner

### Geaendert

- Build-Prozess stabilisiert, damit die EXE aus einem Scratch-Verzeichnis erstellt und danach nach `dist` kopiert wird
- Dialoge fuer Spiel, Mod und SteamCMD sauberer positioniert und zentriert
- Auswahllogik in der Mod-Liste ueberarbeitet
- UI fuer Mod-Zielordner erweitert

### Behoben

- Projektstruktur nach Konfliktdateien wieder auf konsistente Modulpfade zurueckgefuehrt
- Fehler im Dialog-/Eventpfad beim Anlegen neuer Spiele
- Logging beim Anlegen neuer Spiele verbessert
- Bestehende installierte Mod-Ordner werden bei Bedarf auf den konfigurierten Zielordnernamen umbenannt
- Vorhandene Workshop-ID-Ordner werden beim Laden der Modliste mit gespeicherten Zielordnernamen abgeglichen
- Download-Zielpfad nutzt bei gesetztem Zielordnernamen den lokalen benutzerdefinierten Ordner statt nur die Workshop-ID

### Hinweise

- `v0.8` ist der aktuelle in der UI angezeigte Versionsstand.
