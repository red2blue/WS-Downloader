# Development.md

## Projektziel

Es soll eine Python-basierte Desktop-Anwendung entstehen, die Steam Workshop Mods ueber SteamCMD herunterlaedt. Die Anwendung orientiert sich funktional an WorkshopDL, soll aber als eigenes, klar strukturiertes Projekt umgesetzt werden.

Ziel ist eine einfache grafische Oberflaeche, in der Spiele angelegt, Mod-URLs pro Spiel verwaltet und ausgewaehlte Mods per SteamCMD in ein konfiguriertes Zielverzeichnis heruntergeladen werden koennen.

## Referenzen

- WorkshopDL: https://github.com/imwaitingnow/WorkshopDL
- SteamCMD Dokumentation: https://developer.valvesoftware.com/wiki/SteamCMD
- Steam Workshop URLs: https://steamcommunity.com/

## Grundidee

Die Anwendung verwaltet Spiele und deren Workshop-Mods lokal. Pro Spiel wird eine Liste von Mods gespeichert. Mods werden ueber Steam Workshop URLs hinzugefuegt. Aus diesen URLs werden die relevanten IDs ermittelt und mit einer Versionsnummer beziehungsweise einem bekannten Stand gespeichert.

Der Download erfolgt ueber SteamCMD. Die Anwendung soll SteamCMD nicht ersetzen, sondern eine benutzerfreundliche Desktop-Oberflaeche fuer die noetigen SteamCMD-Aufrufe bereitstellen.

## Zielplattform

- Primaer: Windows
- Programmiersprache: Python
- Anwendungstyp: Desktop-Anwendung mit GUI
- Externe Abhaengigkeit: SteamCMD

## Hauptfunktionen

### Spieleverwaltung

- Der Benutzer kann ein neues Spiel anlegen.
- Pro Spiel sollen mindestens folgende Daten gespeichert werden:
  - Steam AppID
  - Workshop-URL
  - Pfad zu den Mods beziehungsweise Downloadverzeichnis
  - Liste der zugeordneten Mods
- Im oberen Bereich der Anwendung soll eine Liste mit den angelegten Spielen angezeigt werden.
- Neben der Spieleliste soll ein Button mit einem Plus-Symbol angezeigt werden.
- Der Plus-Button oeffnet einen Dialog zum Anlegen eines neuen Spiels.
- Der Dialog zum Anlegen eines Spiels enthaelt mindestens folgende Felder:
  - ID des Spiels / Steam AppID
  - URL zum Workshop
  - Pfad zu den Mods beziehungsweise Zielverzeichnis
- Die Informationen zu den Spielen werden nicht in der Datenbank gespeichert, sondern in einer separaten JSON-Datei.
- Die JSON-Datei soll zum Beispiel `games.json` heissen und beim Programmstart geladen werden.
- Aenderungen an Spielen sollen direkt in dieser JSON-Datei persistiert werden.
- Spiele koennen bearbeitet und geloescht werden.
- Beim Loeschen eines Spiels soll eine Sicherheitsabfrage angezeigt werden.

### Mod-Verwaltung

- Innerhalb eines Spiels kann eine Mod-Liste gepflegt werden.
- Wenn ein Spiel ausgewaehlt ist, soll unterhalb der Spieleliste die zugehoerige Modliste angezeigt werden.
- Neben oder oberhalb der Modliste soll ein Button mit einem Plus-Symbol angezeigt werden.
- Der Plus-Button oeffnet einen Dialog zum Hinzufuegen einer neuen Mod.
- Der Dialog zum Hinzufuegen einer Mod enthaelt mindestens ein Feld:
  - Steam Workshop Mod-ID
- Ueber ein Eingabefeld kann die Steam Workshop Mod-ID eingetragen werden.
- Die Anwendung soll aus der Mod-ID die Workshop Item URL ableiten.
- Beim Hinzufuegen eines Mods werden mindestens folgende Daten gespeichert:
  - Mod-Name
  - Mod-URL
  - Workshop Item ID
  - Mod-Version oder gespeicherter Versionsstand
  - Passende Spielversion
  - Neue Version verfuegbar
  - Datum des Hinzufuegens
  - Datum des letzten Downloads
  - Downloadstatus
- Mehrere Mods sollen in einer Liste angezeigt werden.
- Jede Mod in der Liste soll eine Checkbox besitzen.
- Einzelne oder mehrere Mods koennen ueber diese Checkboxen ausgewaehlt werden.
- Mods koennen bearbeitet und geloescht werden.
- Es soll moeglich sein, einzelne oder mehrere Mods fuer Download oder Update auszuwaehlen.

### Versionsverwaltung der Mods

- Zu jedem Mod soll ein Versionsstand gespeichert werden.
- Falls SteamCMD oder Steam-Workshop-Metadaten keine klare semantische Versionsnummer liefern, soll ein technischer Stand gespeichert werden, zum Beispiel:
  - Workshop `time_updated`
  - Dateigruppe/Manifest-Stand, falls verfuegbar
  - Alternativ ein lokaler Zeitstempel des letzten erfolgreichen Downloads
- Die Anwendung soll anzeigen, wann ein Mod zuletzt heruntergeladen wurde.
- Spaeter soll geprueft werden koennen, ob ein Mod seit dem letzten Download aktualisiert wurde.
- Wenn die Modliste geladen ist, soll ein Button `Check for Updates` angezeigt werden.
- Mit `Check for Updates` werden die angezeigten Mods auf neue Versionen beziehungsweise neue technische Versionsstaende geprueft.
- Das Ergebnis der Pruefung soll in der Modliste sichtbar sein, zum Beispiel ueber die Spalte `Neue Version verfuegbar`.
- Der gespeicherte Wert `new_version_available` wird nach der Pruefung aktualisiert.

### Download-Funktion

- Der Benutzer kann ein Downloadverzeichnis pro Spiel eintragen.
- Mit einem Button `Download` werden die ausgewaehlten Mods heruntergeladen.
- Wenn fuer ausgewaehlte Mods eine neue Version verfuegbar ist, koennen diese ueber einen Button `Update` aktualisiert werden.
- Der Button `Update` verwendet die per Checkbox ausgewaehlten Mods.
- Nach erfolgreichem Update werden Versionsstand, `remote_updated_at`, `last_downloaded_at` und Downloadstatus aktualisiert.
- Der Download erfolgt ueber SteamCMD.
- Die Anwendung soll den SteamCMD-Prozess starten und dessen Ausgabe anzeigen oder protokollieren.
- Nach erfolgreichem Download wird der Status des Mods aktualisiert.
- Fehler beim Download sollen sichtbar ausgegeben und gespeichert werden.

### SteamCMD-Integration

- Die Anwendung soll einen Pfad zu `steamcmd.exe` verwalten.
- Beim Programmstart soll geprueft werden, ob SteamCMD verfuegbar ist.
- Die Pruefung soll zuerst den gespeicherten SteamCMD-Pfad verwenden.
- Falls kein gespeicherter Pfad existiert, soll die Anwendung typische Installationspfade pruefen.
- Falls SteamCMD nicht gefunden wird, soll der Benutzer den Pfad manuell auswaehlen koennen.
- Falls SteamCMD nicht gefunden wird, soll ein Dialog angezeigt werden.
- Der Dialog soll erklaeren, dass SteamCMD fuer Downloads erforderlich ist.
- Der Dialog soll einen Link zur offiziellen SteamCMD-Dokumentation enthalten:
  - https://developer.valvesoftware.com/wiki/SteamCMD
- Der Dialog soll Optionen anbieten:
  - SteamCMD-Pfad auswaehlen
  - Link im Browser oeffnen
  - Spaeter einrichten
- Optional spaeter: SteamCMD automatisch herunterladen und einrichten.
- Der Standardaufruf fuer Workshop-Downloads soll konfigurierbar aufgebaut werden.
- Voraussichtliches Kommandomuster:

```text
steamcmd +login anonymous +force_install_dir "<zielverzeichnis>" +workshop_download_item <app_id> <workshop_item_id> +quit
```

- Fuer Spiele oder Mods, die keinen anonymen Download erlauben, soll spaeter ein Login-Modus vorgesehen werden.

## Benutzeroberflaeche

Die GUI soll einfach und klar aufgebaut sein.

Vorgesehene Bereiche:

- Oberer Bereich mit Liste der angelegten Spiele
- Plus-Button neben der Spieleliste zum Anlegen eines Spiels
- Dialog zum Anlegen eines Spiels mit Steam AppID, Workshop-URL und Mod-Pfad
- Bereich unterhalb des ausgewaehlten Spiels mit der zugehoerigen Modliste
- Plus-Button fuer die Modliste zum Hinzufuegen einer Mod
- Dialog zum Hinzufuegen einer Mod mit Steam Workshop Mod-URL
- Mod-Liste mit Checkbox pro Mod
- Button `Check for Updates`
- Button `Update` fuer ausgewaehlte Mods
- Optional zusaetzlich: Button `Download` fuer initiale Downloads
- Status-/Logbereich fuer SteamCMD-Ausgaben

## Datenhaltung

Die Daten sollen lokal gespeichert werden.

### Spielinformationen

Spielinformationen werden in einer separaten JSON-Datei gespeichert.

Vorgesehene Datei:

- `games.json`

Beispielstruktur:

```json
{
  "games": [
    {
      "id": "app-4000",
      "steam_app_id": 4000,
      "game_name": "Garry's Mod",
      "workshop_url": "https://steamcommunity.com/app/4000/workshop/",
      "mods_path": "D:/SteamWorkshop/GarrysMod",
      "install_mode": "subfolder",
      "created_at": "2026-04-26T00:00:00Z",
      "updated_at": "2026-04-26T00:00:00Z"
    }
  ]
}
```

### Mod- und Downloadinformationen

Mod- und Downloadinformationen werden in einer SQLite-Datenbank gespeichert, da Status, Historie und Aktualisierungspruefungen strukturiert verwaltet werden muessen.

Vorgeschlagene Tabellen:

- `mods`
- `downloads`
- `settings`

Vorgesehene Felder fuer `mods`:

- `id`
- `game_id`
- `workshop_item_id`
- `install_folder_name`
- `install_mode` (`inherit`, `subfolder` oder `direct`)
- `mod_name`
- `mod_url`
- `mod_version`
- `compatible_game_version`
- `new_version_available`
- `remote_updated_at`
- `last_downloaded_at`
- `download_status`
- `created_at`
- `updated_at`

Hinweis: `game_id` verweist auf die ID aus der JSON-Datei `games.json`, nicht auf eine `games`-Tabelle.

Installierte Dateien werden zusaetzlich pro Spiel und Workshop-ID unter `install_manifests` im App-Datenordner erfasst. Die Manifeste dienen der Konflikterkennung, dem gezielten Entfernen veralteter Dateien bei Updates und der optionalen Deinstallation, ohne gemeinsam verwaltete Dateien zu loeschen.

## Pruefung: Abrufbarkeit der Mod-Informationen

Die folgenden Informationen sollen gespeichert werden. Nicht alle davon sind direkt ueber SteamCMD abrufbar.

| Information | Direkt ueber SteamCMD abrufbar? | Empfohlene Quelle / Vorgehen |
| --- | --- | --- |
| Mod Name | Nein, nicht verlaesslich als strukturierte Metadaten | Steam Web API `ISteamRemoteStorage/GetPublishedFileDetails` oder Steamworks UGC API |
| Mod URL | Nein | Wird aus Benutzereingabe gespeichert |
| Mod Version | Nein, keine allgemeine semantische Versionsnummer in SteamCMD | Technischer Versionsstand ueber `time_updated`/`rtimeUpdated`, alternativ lokale Downloadhistorie |
| Passende Spielversion | Nicht ueber SteamCMD | Nur verfuegbar, wenn das Spiel Workshop Item Versioning nutzt; Steamworks API `GetSupportedGameVersionData` |
| Neue Version verfuegbar | Nicht direkt | Vergleich gespeicherter `remote_updated_at` mit aktuellem `time_updated`/`rtimeUpdated` |

Ergebnis:

- SteamCMD wird primaer fuer den Download verwendet.
- SteamCMD kann den Workshop-Download ausfuehren, liefert aber keine stabile, vollstaendige Metadaten-Schnittstelle fuer Name, Mod-Version, passende Spielversion oder Update-Status.
- Fuer Metadaten soll eine separate Metadata-Komponente vorgesehen werden.
- Fuer oeffentlich abrufbare Workshop-Basisdaten kann `ISteamRemoteStorage/GetPublishedFileDetails` genutzt werden.
- Die passende Spielversion ist nur dann sauber abrufbar, wenn das jeweilige Spiel Steam Workshop Item Versioning aktiviert und gepflegt hat.
- Wenn keine echte Mod-Version verfuegbar ist, wird `remote_updated_at` als technischer Versionsstand verwendet.

## Technische Anforderungen

- Python-Projekt mit sauberer Modulstruktur
- Trennung von GUI, Datenhaltung und SteamCMD-Ausfuehrung
- Keine hart codierten lokalen Pfade
- SteamCMD-Verfuegbarkeit beim Start pruefen
- Robuste Fehlerbehandlung bei ungueltigen URLs, fehlendem SteamCMD, fehlenden Schreibrechten und SteamCMD-Fehlern
- Logdatei fuer Downloads und Fehler
- Konfigurierbarer Speicherort fuer Einstellungen und Datenbank

## Nicht-Ziele fuer die erste Version

- Kein eigener Steam-Client
- Kein Umgehen von Steam-Beschraenkungen oder DRM
- Kein Download von Inhalten, fuer die ein Benutzer keine Berechtigung hat
- Keine vollautomatische Mod-Installation in Spielverzeichnisse
- Keine Unterstuetzung mehrerer Download-Provider ausser SteamCMD
- Keine Workshop-Collection-Unterstuetzung in der ersten Version

## Rechtliche und Nutzungsbedingungen

- Die Anwendung soll SteamCMD regulaer verwenden.
- Downloads muessen im Rahmen der Steam- und Workshop-Bedingungen erfolgen.
- Die Anwendung darf keine Schutzmechanismen umgehen.
- Bei Spielen, die Login oder Besitz voraussetzen, muss der Benutzer die noetigen Rechte besitzen.

## Offene Fragen

- Welches GUI-Framework soll verwendet werden?
  - Optionen: PySide6, PyQt, Tkinter, CustomTkinter
- Soll SteamCMD automatisch heruntergeladen und aktualisiert werden?
- Soll ein Steam-Login direkt in der Anwendung unterstuetzt werden?
- Soll die Anwendung Workshop-Metadaten ueber Steam Web API abrufen?
- Soll es einen Import fuer Textdateien mit mehreren Mod-URLs geben?
- Soll es eine Exportfunktion fuer Mod-Listen geben?
- Wie genau soll die Versionsnummer dargestellt werden, wenn Steam keine sichtbare Mod-Version liefert?

## Vorschlag fuer erste Umsetzungsschritte

1. Python-Projektstruktur anlegen.
2. GUI-Framework festlegen.
3. Lokale Datenhaltung fuer Spiele und Mods implementieren.
4. URL-Parser fuer Steam Workshop URLs erstellen.
5. SteamCMD-Pfad und Downloadverzeichnis konfigurierbar machen.
6. SteamCMD-Prozess aus Python starten und Ausgabe in der GUI anzeigen.
7. Downloadstatus und Fehler speichern.
8. Erste testbare Version mit einem Spiel und mehreren Mods fertigstellen.

## Akzeptanzkriterien fuer Version 1

- Beim Programmstart wird geprueft, ob SteamCMD verfuegbar ist.
- Wenn SteamCMD fehlt, erscheint ein Dialog mit Link zur offiziellen SteamCMD-Dokumentation.
- Ein Spiel kann angelegt und gespeichert werden.
- Angelegte Spiele werden im oberen Bereich der Anwendung angezeigt.
- Ein Plus-Button neben der Spieleliste oeffnet einen Dialog zum Anlegen eines Spiels.
- Der Spieldialog speichert Steam AppID, Workshop-URL und Mod-Pfad in `games.json`.
- Fuer ein Spiel koennen mehrere Mod-URLs hinzugefuegt werden.
- Wenn ein Spiel ausgewaehlt ist, wird darunter die zugehoerige Modliste geladen.
- Ein Plus-Button bei der Modliste oeffnet einen Dialog zum Hinzufuegen einer Mod-URL.
- Die Anwendung extrahiert die Workshop Item ID aus gueltigen Steam Workshop URLs.
- Mods werden mit Versionsstand oder lokalem Downloadstand gespeichert.
- Jede Mod kann per Checkbox ausgewaehlt werden.
- `Check for Updates` prueft die angezeigten Mods auf neue Versionen beziehungsweise neue technische Versionsstaende.
- `Update` aktualisiert die per Checkbox ausgewaehlten Mods.
- Ein Zielverzeichnis kann ausgewaehlt werden.
- Ausgewaehlte Mods koennen per SteamCMD heruntergeladen werden.
- Downloadausgabe und Fehler werden in der Anwendung angezeigt.
- Daten bleiben nach Neustart der Anwendung erhalten.

## Umsetzungsprotokoll

### Bereits umgesetzt

1. Python-Projektstruktur angelegt.
2. GUI als Tkinter-Anwendung erstellt.
3. Lokale Speicherung fuer Spiele in `games.json` implementiert.
4. SQLite-Datenbank fuer Mods, Downloads und Settings angelegt.
5. Steam Workshop URLs werden geparst und die Workshop Item ID wird extrahiert.
6. Workshop-Metadaten werden ueber die Steam Web API abgefragt, soweit verfuegbar.
7. SteamCMD-Pfad wird beim Start gesucht und kann manuell gesetzt werden.
8. Dialog erscheint, wenn SteamCMD fehlt.
9. Spiele koennen angelegt, bearbeitet und geloescht werden.
10. Mods koennen pro Spiel angelegt, bearbeitet und geloescht werden.
11. Checkbox-Auswahl fuer Mods ist in der Liste vorhanden.
12. `Check for Updates` vergleicht gespeicherte und aktuelle Metadaten.
13. `Download` und `Update` starten SteamCMD-Aufrufe fuer ausgewaehlte Mods.
14. Downloadausgabe wird in der GUI und in einer Logdatei protokolliert.
15. Ein technischer Versionsstand wird auch dann gespeichert, wenn keine klare semantische Versionsnummer verfuegbar ist.
16. Syntax-Checks fuer die aktuelle Implementierung wurden erfolgreich durchgefuehrt.
17. Windows-Build-Helfer fuer eine spaetere `.exe`-Erzeugung vorbereitet (`build.ps1`, `build.bat`, `requirements-build.txt`).
18. Ein lauffaehiger PyInstaller-Build wurde erfolgreich erzeugt.
19. Spiele koennen jetzt nur noch ueber die Steam AppID angelegt werden; Workshop-URL und Spielname werden automatisch abgeleitet.
20. Spielnamen und Modnamen werden, sofern verfuegbar, automatisch aus Steam-Metadaten nachgezogen und in der Liste angezeigt.
21. Der Mod-Dialog fragt jetzt nur noch die Steam Workshop Mod-ID ab; der Name wird aus Metadaten abgeleitet.
22. Der Mod-Dialog verwendet keine lange Workshop-URL mehr, sondern nur noch die numerische Mod-ID.
23. Downloads laufen jetzt ueber einen temporären Arbeitsordner, danach wird nur der Mod-Ordner mit der Workshop-ID in das Zielverzeichnis verschoben.
24. Die Mod-Liste im unteren Bereich wird zentriert dargestellt.
25. Zukuenftig soll optional eine Sicherung alter Mod-Versionen vor dem Ueberschreiben moeglich sein.
26. Spiele besitzen eine Standard-Installationsart (`subfolder` oder `direct`), die pro Mod geerbt oder ueberschrieben werden kann.
27. Direkte Installationen kopieren den Inhalt ohne umschliessenden Workshop-ID-Ordner in das Mod-Verzeichnis.
28. Dateimanifeste und ein Bestaetigungsdialog schuetzen vor unbemerkten Ueberschreibkonflikten.
26. Dialogfenster werden zentriert ueber dem Hauptfenster angezeigt.

### Noch offen

1. GUI optisch und ergonomisch weiter verfeinern.
2. Update- und Download-Fehlerfaelle in der GUI noch klarer darstellen.
3. SteamCMD-Login-Modus fuer Spiele mit Besitz- oder Login-Pflicht vorbereiten.
4. Import von mehreren Mod-URLs aus Textdateien ergaenzen.
5. Exportfunktion fuer Mod-Listen ergaenzen.
6. SteamCMD-Auto-Download und Auto-Setup optional vorbereiten.
7. Download-Historie in der GUI sichtbar machen.
8. Bessere Validierung fuer Spielpfade und Schreibrechte ergaenzen.
9. Tests fuer URL-Parsing, Persistenz und SteamCMD-Kommandoaufbau ausbauen.
10. Bei Bedarf das Datenmodell weiter an echte Workshop-Metadaten anpassen.
11. Optional ein Icon und eine Versionsanzeige fuer die gebaute `.exe` ergaenzen.
12. Optional alte Mod-Versionen beim Update sichern, statt sie sofort zu ueberschreiben.
