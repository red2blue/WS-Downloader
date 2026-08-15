# WS Downloader Kurzinfo

Windows-Tool zum Herunterladen und Aktualisieren von Steam-Workshop-Mods per SteamCMD.

## Schnellstart

1. `WS Downloader.exe` starten.
2. SteamCMD auswaehlen oder mit `SteamCMD installieren` automatisch einrichten.
3. Spiel mit Steam-App-ID, Mod-Ordner und Installationsart anlegen.
4. Mods per Workshop-ID hinzufuegen und bei Bedarf eine abweichende Installationsart waehlen.
5. Mods auswaehlen und herunterladen oder Updates pruefen.

Mods koennen jeweils in einem eigenen Unterordner oder direkt im Mod-Verzeichnis installiert werden. Direkte Installationen werden ueber Dateimanifeste verfolgt; erkannte Ueberschreibkonflikte muessen bestaetigt werden.

SteamCMD wird beim Start bzw. nach der Konfiguration mit `steamcmd +quit` geprueft und aktualisiert sich dabei selbst, falls Valve ein Update bereitstellt.
