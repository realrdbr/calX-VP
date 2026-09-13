# Datenschutz im Betrieb

Die Datenschutzerklärung bildet die Anwendung ab, ersetzt aber keine Prüfung der konkreten Betreiberpflichten. Eine Zugangsbeschränkung begründet nicht automatisch die Haushaltsausnahme. Name und Anschrift werden ausschließlich aus der lokalen `.env` übernommen und auf der Datenschutzerklärung veröffentlicht. Die `.env` ist von Git und Docker-Build-Kontext ausgeschlossen.

`SUPPORT_MAIL`, `PRIVACY_CONTROLLER`, `PRIVACY_ADDRESS`, `PRIVACY_PROCESSORS` und `PRIVACY_RETENTION` werden zur Laufzeit in beiden Diensten verwendet. Die Werte sind öffentlich. Nach einer Änderung Docker-Container neu erstellen. Name und Hosting entsprechen den Betreiberangaben; nginx ist selbst betriebene Software, kein eigener Empfänger. STRATO-Vertrag zur Auftragsverarbeitung und tatsächlichen Rechenzentrumsstandort prüfen. Eventuelle externe Push-Dienste hängen von ntfy- und App-Konfiguration ab.

## Zusätzliches Löschkonzept – noch einzurichten

- Alte nginx-Dateilogs und globale Hostlogs: nach spätestens 7 Tagen löschen, einschließlich komprimierter Dateien.
- Dokumentierte Sicherheitsvorfälle: nur erforderliche Auszüge bis zur Klärung separat aufbewahren. Normale Anmeldeprotokolle werden automatisch nach 30 Tagen stündlich bereinigt.
- Versandnachweise: bis 30 Tage nach dem zugehörigen Termin; nicht vor dem Termin löschen, sonst droht erneuter Versand.
- Backups: Die optionale Projektfunktion bereinigt nach einem Kalendermonat bei aktivem Backupbetrieb. Bei Wiederherstellung zwischenzeitliche Löschungen erneut anwenden.
- Kontolöschungen: nach Identitätsprüfung innerhalb eines Monats bearbeiten; gemeinsame Einträge auf notwendige Weiterverwendung prüfen und Autorenbezug gegebenenfalls entfernen.
- Verwaiste Uploads: regelmäßige Zuordnungsprüfung; nach 7 Tagen ohne Referenz löschen. Vorhandene Anhänge an gültigen Terminen nicht löschen.

Die Anwendung bereinigt alte Kalendereinträge bereits nach 18 Monaten. Die oben vorgeschlagenen zusätzlichen Fristen sind noch keine durchgehend implementierte Löschroutine. Erst nach Einrichtung und Prüfung darf `PRIVACY_RETENTION` sie als tatsächlich geltend ausweisen. Insbesondere größenbasierte Docker-Logrotation garantiert keine zeitliche Löschung.

Produktion über HTTPS betreiben und `COOKIE_SECURE=true` setzen. Die PIN-Pflicht nutzt weiterhin das vorhandene vierstellige PIN-System; Konten mit bestehender persönlicher PIN werden nicht umgestellt. Beim erstmaligen Setzen werden andere Sitzungen widerrufen. Noch ungeschützte Konten können vor der Erstvergabe nur durch Kenntnis des Benutzernamens beansprucht werden; die Erstvergabe daher zeitnah mit den vorgesehenen Nutzern durchführen.

## Containerlogs ohne zusätzlichen Dienst oder Port

Compose verwendet den nativen Docker-Treiber `journald`. Das setzt einen Linux-Docker-Host mit systemd-journald voraus. `docker logs CONTAINER` und `docker compose logs --tail=200 app vp` funktionieren weiterhin. nginx benötigt keine Konfigurationsänderung.

Die Frist wird von journald auf dem Host verwaltet, nicht von Compose. Die Änderung von `.env` allein aktiviert daher keine Löschung. Der Betreiber hat der Aufbewahrung von 7 Tagen für das **gesamte Systemjournal** ausdrücklich zugestimmt. Andere dort gespeicherte Serverlogs sind ebenfalls betroffen.

Vom Projektverzeichnis auf dem Server aus:

```sh
# Konfiguration zuerst anzeigen; liest ausschließlich LOG_RETENTION_DAYS.
python3 ops/configure_journal.py
# Hostkonfiguration und stündliche Bereinigung einrichten.
sudo python3 ops/configure_journal.py --install
# Bestehende Container mit dem neuen Logging-Treiber neu erstellen.
docker compose up -d --build
# Logs wie gewohnt lesen.
docker compose logs --tail=200 app vp
```

Das Skript benötigt nur Python 3. Es liest die `.env` als Text und führt keine Shellbefehle daraus aus. Es installiert eine journald-Drop-in-Datei und eine systemd-Service-/Timerdatei. `MaxRetentionSec` legt die Aufbewahrung fest, `MaxFileSec=1h` begrenzt Journaldateien zeitlich. Der stündliche Timer rotiert und bereinigt archivierte Dateien zusätzlich, auch bei geringem Logaufkommen. journald löscht ganze Dateien, nicht einzelne Zeilen; Rotation und Prüfintervall können die tatsächliche Verweildauer verlängern. Während der Server ausgeschaltet ist, läuft keine Bereinigung. Speicherlimits des Hosts können früher löschen.

Prüfen:

```sh
systemctl status cal11-journal-retention.timer
systemctl cat cal11-journal-retention.service
journalctl -u cal11-journal-retention.service --since today
systemd-analyze cat-config systemd/journald.conf
```

Später geladene journald-Drop-ins können Werte überschreiben. Nach Änderungen an `LOG_RETENTION_DAYS` das Installationsskript erneut ausführen und die Datenschutzerklärung anpassen. Das Skript führt keine Änderung am Docker-Daemon oder nginx durch. Erst das Neu-Erstellen der Projektcontainer wechselt deren Logging-Treiber; alte Docker-Dateilogs verschwinden mit den ersetzten Containern.

Separate nginx-Dateilogs, rsyslog-Kopien und Backups unterliegen ihren eigenen Hostregeln. Diese werden nicht durch Journal-Vacuum gelöscht. Die Datenbank-Anmeldeprotokolle werden von Kalender und VP-Worker beim Start und stündlich nach 30 Tagen bereinigt.

## Verifikation

Die Regressionstests prüfen PIN-Pflicht, Überschreibschutz, gelöschte und verschobene Termine, aktuelle Kurszuordnung sowie die sichere Erzeugung der Journal-Konfiguration. `tests/sql-privacy-pin.test.ts` läuft nur mit `CAL11_SQL_INTEGRATION=1` gegen die ausdrücklich isolierte Datenbank `regression` auf Host `database` und ist im normalen Testlauf deaktiviert.

Kalendererinnerungen werden nur zum errechneten Versandtermin mit einem Nachholfenster von 20 Minuten gesendet. Alte Erinnerungen werden nicht an späteren Tagen nachgeholt. Vor dem Versand werden aktueller Datensatz, Löschstatus, Kurszuordnung und Benachrichtigungseinstellungen erneut gelesen. Eine bereits zugestellte Push-Mitteilung kann dadurch nicht rückwirkend geändert werden.

Beim Start über `./start-all.sh docker` oder `./start-all.sh docker-proxy` wird die
Journal-Einrichtung automatisch geprüft und bei Bedarf mit `sudo` ausgeführt.
Das Passwort wird ausschließlich von sudo abgefragt. Nach erfolgreicher Einrichtung
speichert `.local-state/journal-retention` eine lokale, vom Versionsstand und Host
abhängige Markierung; dieser Ordner wird weder committed noch ins Docker-Image kopiert.
Bei geänderter Aufbewahrungsfrist, fehlender Konfiguration oder deaktiviertem Timer
wird die Einrichtung wiederholt. Ein Fehler bricht den Start vor Containeränderungen ab.
Der Modus `local` verändert das Systemjournal nicht.

## Prüfung der Erklärung und Trennung der Konfiguration

- `.env`: Name, ladungsfähige Anschrift, Supportkontakt, tatsächliche Dienstleister,
  eingesetzte Betriebssoftware, vom Betrieb abhängige Aufbewahrung und die zum
  Betreiberstandort passende Aufsichtsbehörde (`PRIVACY_AUTHORITY`). Diese Angaben
  werden veröffentlicht; hier dürfen keine Schlüssel oder Zugangsdaten stehen.
- `public/privacy.json`: Verarbeitung durch die Anwendung, Herkunft und Kategorien
  der Daten, Rechte, konkrete Hash-/Verschlüsselungsverfahren und deren Grenzen.
  Bei Codeänderungen diese Aussagen mitprüfen. Keine personenbezogenen Betreiber-
  angaben in diese Datei übernehmen.
- `public/legal-defaults.json` und `.env.example`: generische Hinweise für andere
  Betreiber. Platzhalter sind kein Ersatz für eine ausgefüllte Erklärung.

### Noch nicht durch Textänderungen belegbar

Der Betreiber hat bestätigt, dass die Schule ihre Pläne auf stundenplan24
veröffentlicht, aber keine ausdrückliche Zustimmung zur Weiterverwendung durch
sein Projekt erteilt hat. Veröffentlichung und Schulzugangsdaten allein belegen
keine Erlaubnis. Vor einer uneingeschränkten Rechtmäßigkeitszusage müssen die
Nutzungsbedingungen, die Rollen der Beteiligten und die konkrete Rechtsgrundlage
für Lehrkraft- und andere personenbezogene Plandaten geprüft und dokumentiert
werden; die Interessenabwägung nach Art. 6 Abs. 1 lit. f ist keine pauschale Erlaubnis.
Art.-14-Informationen müssen betroffene Personen tatsächlich erreichen; die bloße
Existenz dieser Seite belegt deren ordnungsgemäße Unterrichtung noch nicht.

Ein Auftragsverarbeitungsvertrag mit STRATO ist noch nicht bestätigt. Für externe
Push-Empfänger müssen die tatsächlich beteiligten Rechtsträger, Rollen und die
Transfergrundlage nach Art. 44 ff. DSGVO anhand der Verträge geprüft werden.
Eine ntfy-Einstellung ersetzt weder einen AV-Vertrag noch Transfergarantien.
Das frühere Backupskript ist noch nicht geprüft. Die neue optionale
Backupfunktion ist in `docs/backups.md` beschrieben; bestehende externe Sicherungen
werden von deren Monatsregel nicht erfasst. Für verwaiste Uploads und Versandnachweise fehlt automatische Bereinigung.
Diese Tatsachen dürfen nicht durch erfundene Fristen oder Zusicherungen ersetzt werden.

### nginx-Dateilogs

`start-all` richtet neben journald `/etc/logrotate.d/nginx` ein und aktiviert den
vorhandenen `logrotate.timer`. Voraussetzung ist ein installiertes logrotate-Paket
mit systemd-Timer. Die vorherige nginx-Rotationsregel wird einmalig nach
`/etc/nginx-logrotate.cal11-original` gesichert. Eine Friständerung oder diese neue
Regel ändert den Fingerabdruck und löst die Einrichtung erneut aus.

Erfasst werden ausschließlich reguläre nginx-Logpfade `/var/log/nginx/*.log`.
Tägliche Rotation (auch bei leeren Dateien), `rotate 7` und `maxage 7` begrenzen
Archive; für aktive Dateien kommt das laufende Tagesintervall hinzu. nginx bekommt
über seinen systemd-Dienst USR1 zum Wiederöffnen der Logs. Abweichende Pfade,
anders gestartete nginx-Prozesse und bestehende Archive anderer Rotationsschemata
müssen gesondert geprüft werden. Die Proxy-Konfiguration wird nicht verändert.

### Quellen der Prüfung

- DSGVO, insbesondere Art. 5, 6, 12–14, 21, 28, 32, 44 ff. und 77:
  https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:32016R0679
- Anbieterkennzeichnung: https://www.gesetze-im-internet.de/ddg/__5.html
- Aktuelle Aufsichtskontaktdaten: https://www.datenschutz.sachsen.de/kontakt.html
- ntfy: https://docs.ntfy.sh/privacy/ und https://docs.ntfy.sh/config/#ios-instant-notifications
- Logrotate: https://github.com/logrotate/logrotate/blob/main/logrotate.8.in
