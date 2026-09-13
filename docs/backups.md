# Backups und Wiederherstellung

Start mit täglicher Sicherung:

```sh
./start-all --backups
# Mit Compose-Proxy:
./start-all docker-proxy --backups
# SSH-unabhängig im Hintergrund:
./start-all -d --backups
# Hintergrundbetrieb inklusive Abschlussbackup beenden:
./start-all --stop
```

Backups werden täglich um 00:00 Uhr in `APP_TIMEZONE` (Standard `Europe/Berlin`)
erstellt. Beim Start wird die nächste Mitternacht geplant; es gibt kein zusätzliches
Startbackup. Sommer- und Winterzeit werden berücksichtigt. Beim regulären Beenden von start-all endet zuerst der Worker. Mit `--backups` wird
danach zusätzlich ein Abschlussbackup erstellt, bevor die Container herunterfahren.
Bei Stromausfall oder `kill -9` ist das nicht möglich. Bei einem Backupfehler wird
eine Warnung ausgegeben und mit Fehlerstatus heruntergefahren.
`./start-all` ohne Schalter erstellt keine Backups und startet keinen Backup-Timer.
Die Einstellung wird nicht gespeichert. Ohne laufenden Worker findet auch keine
periodische Backupbereinigung statt; beim nächsten Start mit `--backups` und bei jedem Backup wird wieder bereinigt.

Mit `-d` übernimmt eine vom Terminal getrennte Hintergrundsteuerung den Worker und
das Abschlussbackup. Eine geschlossene SSH-Verbindung oder das Beenden von
`docker compose logs -f` stoppt diesen Betrieb nicht. Zum geordneten Beenden immer
`./start-all --stop` verwenden. Vor einem Start ohne Backups den bestehenden Betrieb
stoppen; parallele start-all-Starts werden abgewiesen. Nach einem Serverneustart muss
die Backupsteuerung erneut mit `./start-all -d --backups` gestartet werden.

`backups/` und `.local-state/` sind von Git und Docker-Builds ausgeschlossen.
Backups erhalten AES-256-GCM-Verschlüsselung mit Integritätsprüfung. Der zufällige
32-Byte-Schlüssel liegt in `.local-state/backup.key` (0600), getrennt vom Archiv.
**Diesen Schlüssel separat und sicher aufbewahren. Ohne ihn sind die Backups nicht
wiederherstellbar.** Ein Schlüssel auf demselben Server schützt nicht vor einem
Angreifer mit vollständigem Serverzugriff. Externe Kopien haben eigene Löschfristen.

Enthalten sind ein transaktionaler MariaDB-Dump, separate konsistente SQLite-
Snapshots von ntfy, Uploads und die `.env` einschließlich notwendiger Schlüssel.
Die Snapshots sind nicht dienstübergreifend atomar. Während des Exports angelegte
Anhänge können daher einen anderen Stand als der Datenbankdump haben. Temporäre
Klartextdateien liegen während der Erstellung in einem privaten Verzeichnis und
werden nach Abschluss entfernt. Backups bekommen 0600, der Ordner 0700.

Archive liegen nach Datum gruppiert unter `backups/JJJJ-MM-TT/`. Bestehende flache
Archive werden beim aktivierten Backupbetrieb entsprechend einsortiert. Archive
werden einen Kalendermonat nach ihrer Erstellung beim nächsten Prüflauf gelöscht
(z. B. 31. Januar → 28./29. Februar). Der tägliche Prüfabstand kann einen zusätzlichen
Tag ergeben. Maßgeblich ist der Zeitstempel im Archivnamen, nicht das Änderungsdatum
der Datei; leere Datumsordner werden entfernt.
Andere Dateien und Backups fremder Skripte werden nicht gelöscht.

Wiederherstellung auf derselben Installation:

```sh
./start-all --restore backups/JJJJ-MM-TT/cal11-DATUM-ZUFALL.tar.gz.enc
# Optional anschließend wieder tägliche Sicherungen aktivieren:
./start-all --restore backups/JJJJ-MM-TT/cal11-DATUM-ZUFALL.tar.gz.enc --backups
```

Vorher andere start-all-Instanzen beenden. Docker und die Projektimages sind erforderlich. Nach Bestätigung wird der aktuelle
Stack für die Sicherheitskopie gestartet, falls er noch nicht läuft. Das Archiv wird vollständig authentifiziert, Pfade und
Dateitypen geprüft und die Datenbank-/Verschlüsselungskonfiguration abgeglichen.
Bei abweichenden Schlüsseln oder Datenbankzugängen wird vor Änderungen abgebrochen.
`.env` wird nicht automatisch überschrieben. Bei einem neuen Server zunächst die
passende Konfiguration und Images aus dem gesicherten Projektstand bereitstellen.

Erst nach Eingabe von `WIEDERHERSTELLEN` wird eine zusätzliche Sicherung des aktuellen
Zustands erstellt. Dann werden schreibende Dienste gestoppt und Datenbank, ntfy-Daten
und Uploads ersetzt. Gesicherte Sitzungen werden widerrufen. Anschließend startet
start-all die Dienste neu. Bei einem Fehler während der Wiederherstellung bleiben
die gestoppten Dienste zur Diagnose gestoppt; kein automatischer Rollback.

Zum manuellen Entschlüsseln in einer Umgebung mit Python und `cryptography`:

```sh
python ops/backup_crypto.py decrypt .local-state/backup.key BACKUP.enc OUTPUT.tar.gz
```

Die Ausgabedatei darf noch nicht existieren. Sie enthält vertrauliche Daten und
Zugangsdaten. Nur in einer geschützten Umgebung verwenden und nach Gebrauch entfernen.

## Alte Datenbanken

Beim Start ergänzen Kalender und VP fehlende Spalten für ältere Projektschemata.
Bestehende Konten, PIN-Werte, Kurse und Termine bleiben dabei erhalten (abgesehen
von regulären Löschfristen). Neue PINs benötigen gegebenenfalls die automatisch
verbreiterte PIN-Spalte. Ein Konto ohne PIN muss weiterhin eine persönliche PIN
festlegen. Auch das Einspielen eines alten Backups wird beim folgenden Start durch
diese Migrationen ergänzt.

Geprüft sind reduzierte frühere SQLite-Tabellen sowie MariaDB-Tabellen für Nutzer,
Termine, Kurse und Kategorien, einschließlich zweimaligem Start derselben Datenbank.
Unbekannte Fremdschemata oder manuell veränderte Tabellen sind damit nicht pauschal
abgedeckt. Der explizite SQL-Test läuft nur gegen eine isolierte Datenbank:

```sh
docker compose -p cal11-legacy-test -f tests/sql-legacy-compose.yml up --abort-on-container-exit --exit-code-from tester
docker compose -p cal11-legacy-test -f tests/sql-legacy-compose.yml down -v
```
