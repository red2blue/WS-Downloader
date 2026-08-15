# WS Downloader

`WS Downloader` ist ein kleines Windows-Tool zum Verwalten und Aktualisieren von Steam-Workshop-Mods ueber SteamCMD.

## Zweck

Das Tool richtet sich an Spiele, bei denen Workshop-Mods lokal in einen bestimmten Mod-Ordner kopiert werden muessen. Es speichert Spiele, Mods und Zielordner, startet SteamCMD fuer Downloads und kann installierte Mods auf bekannte Workshop-IDs zurueckfuehren.

## Verwendung

1. `WS Downloader.exe` starten.
2. SteamCMD konfigurieren. Wenn SteamCMD fehlt, kann es ueber den Button `SteamCMD installieren` automatisch in den App-Datenordner geladen und eingerichtet werden.
3. Spiel mit Steam-App-ID und lokalem Mod-Ordner anlegen.
4. Installationsart des Spiels festlegen: eigener Unterordner pro Mod oder Inhalt direkt in den Mod-Ordner.
5. Mods ueber Workshop-ID hinzufuegen.
6. Optional Installationsart und lokalen Zielordner fuer einzelne Mods abweichend konfigurieren.
7. Mods auswaehlen und herunterladen oder auf Updates pruefen.

## Funktionen

- Verwaltung mehrerer Spiele mit eigener Steam-App-ID und eigenem Mod-Verzeichnis.
- Download von Workshop-Mods per SteamCMD.
- Automatische SteamCMD-Pruefung durch Starten von `steamcmd +quit`; SteamCMD aktualisiert sich dabei selbst, wenn ein Update vorliegt.
- Automatische SteamCMD-Installation ueber den offiziellen Windows-Installer-Zip.
- Benutzerdefinierte lokale Zielordnernamen pro Mod.
- Spielweiter Standard fuer Installationen im eigenen Unterordner oder direkt im Mod-Verzeichnis.
- Optionale Installationsart pro Mod: Spieleinstellung, eigener Unterordner oder direkte Installation.
- Dateimanifeste zur Zuordnung direkt installierter Dateien zur Workshop-ID.
- Konfliktwarnung vor dem Ueberschreiben vorhandener oder von anderen Mods verwalteter Dateien.
- Optionales Entfernen der laut Manifest zu einer Mod gehoerenden Dateien beim Loeschen des Mod-Eintrags.
- Uebernahme eines Dateinamens als Zielordnername ohne Dateiendung.
- Auswahl aller sichtbaren Mods ueber `+/-`.
- Markierung von Mods mit verfuegbarer neuer Version.
- Changelog und Versionsanzeige in der Anwendung.

## Hinweise

- Fuer den Download ist eine Internetverbindung erforderlich.
- SteamCMD kann je nach Spiel anonyme Workshop-Downloads erlauben oder ablehnen. Das ist eine Steam-/Spiel-Einschraenkung.
- Die Zuordnung zur Workshop-ID bleibt gespeichert, auch wenn lokal ein anderer Zielordnername verwendet wird.
- Bestehende Spiele verwenden nach dem Update weiterhin automatisch einen eigenen Unterordner pro Mod.
- Bei direkter Installation koennen mehrere Mods dieselben Dateien verwenden. Vor dem Ueberschreiben zeigt WS Downloader die erkannten Konflikte an und verlangt eine Bestaetigung.
- Installationsmanifeste werden im App-Datenordner unter `install_manifests` gespeichert.

## KI-Unterstuetzung und Haftung

Dieses Projekt und sein Quellcode wurden mit Unterstuetzung generativer KI entwickelt. Obwohl die Ergebnisse geprueft und praktisch getestet wurden, koennen Fehler, unerwartetes Verhalten oder Inkompatibilitaeten nicht ausgeschlossen werden.

Die Software wird ohne Gewaehrleistung bereitgestellt. Die Nutzung erfolgt auf eigene Verantwortung und eigenes Risiko. Die Autoren und Mitwirkenden haften nicht fuer Schaeden, Datenverluste oder sonstige Folgen, die unmittelbar oder mittelbar aus der Installation oder Verwendung der Software entstehen.
