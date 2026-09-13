# Reverse-proxy templates

These templates expose three separate HTTPS hostnames:

- `cal11.de` -> Kalender (Node/React) on `app:3000`
- `vp.cal11.de` -> Vertretungsplan (Python) on `vp:8000`
- `notify.cal11.de` -> ntfy on `ntfy:80`

Replace the example hostnames and certificate settings first. Set these values in `.env`:

```dotenv
CALENDAR_PUBLIC_URL=https://cal11.de
VERTRETUNGSPLAN_PUBLIC_URL=https://vp.cal11.de
NTFY_PUBLIC_URL=https://notify.cal11.de
NTFY_BEHIND_PROXY=true
APP_BIND_HOST=127.0.0.1
VP_BIND_HOST=127.0.0.1
NTFY_BIND_HOST=127.0.0.1
COOKIE_SECURE=true
COOKIE_DOMAIN=cal11.de
```

`COOKIE_DOMAIN` wird für die dokumentierte Kombination `cal11.de` und
`vp.cal11.de` automatisch aus den öffentlichen URLs erkannt. Die explizite
Angabe bleibt für abweichende Domainstrukturen empfohlen. Der Wert darf nur
die gemeinsame Eltern-Domain enthalten; der Provisionierungsdienst und ntfy
benötigen diese Session-Cookies nicht.

Compose fixes server-side delivery to `http://ntfy-delivery` on the separate internal network; do not replace it with the public domain. Client subscriptions continue to use `https://notify.cal11.de`. Set `NTFY_BEHIND_PROXY=true` in `.env` when the proxy is the public entry point. The proxy must pass WebSocket upgrades and must not buffer ntfy streaming responses. Do not expose port 8090 publicly; the Compose template binds it to localhost.

For nginx, the calendar vhost in [nginx.conf](/home/rdbr/PycharmProjects/jahrgangskalender/proxy/nginx.conf) already includes upload-safe settings for `/api/upload` (`client_max_body_size 15m`, `proxy_request_buffering off`). Keep this when adjusting templates, otherwise uploads can fail with HTTP 413.

Kalender und VP lesen `TRUSTED_PROXIES`. Compose übergibt die Einstellung an beide
Dienste und aktiviert `TRUST_DOCKER_GATEWAY`: Innerhalb der Container wird ausschließlich
die konkrete IPv4-Standardgateway-Adresse aus der Routingtabelle vertraut. Damit
funktioniert ein Host-nginx über die an Loopback gebundenen Docker-Ports, ohne pauschal
private Netze freizugeben. Der optionale Caddy wird über `TRUSTED_PROXY_HOSTS=proxy`
aufgelöst; seine konkreten Adressen werden regelmäßig aktualisiert. Für externe
Proxycontainer eigene kontrollierte DNS-Namen oder exakte IPs eintragen.

Alle Backend-Ports müssen von außen unzugänglich sein (`APP_BIND_HOST`, `VP_BIND_HOST`,
`NTFY_BIND_HOST` jeweils `127.0.0.1`). Andernfalls kann bei Docker-Portweiterleitung
die Herkunft eines direkten Aufrufs nicht sicher vom Hostproxy unterschieden werden.
nginx, Caddy und Apache überschreiben eingehende Forwarding-Header. Traefik muss mit
der ergänzten `traefik-static.yml` beziehungsweise deren `forwardedHeaders`-Einstellungen
betrieben werden; `insecure` bleibt `false`, ohne pauschale `trustedIPs`. Bei einem
zusätzlichen vorgeschalteten CDN sind dessen konkrete Vertrauensgrenzen gesondert
zu konfigurieren; die Beispiele behandeln den direkt erreichbaren Edge-Proxy.

Nach Änderungen Container neu erstellen und den tatsächlich installierten Hostproxy
prüfen und neu laden. `.env` und Repositoryvorlagen aktualisieren keine außerhalb
des Projekts liegende nginx-Konfiguration automatisch.

The ntfy iOS flow still requires `upstream-base-url: "https://ntfy.sh"` in `ntfy/server.yml`, plus the user's ntfy credentials in the mobile app. The topic link opens the web view, but it does not carry authentication.

Sources:

- https://docs.ntfy.sh/config/#behind-a-proxy-tls-etc
- https://docs.ntfy.sh/config/#ios-instant-notifications
- https://nginx.org/en/docs/http/websocket.html
- https://httpd.apache.org/docs/2.4/mod/mod_proxy.html
- https://caddyserver.com/docs/caddyfile/directives/reverse_proxy

For production with nginx running on the Docker host, use `./start-all.sh docker`
(the `docker-proxy` mode starts the optional Caddy service and would compete for
ports 80/443). Keep the existing production TLS certificate directives when
applying the proxy template. Validate the installed configuration with `nginx -t`
before reloading nginx. The internal publisher URL is independent of nginx and
must remain `http://ntfy-delivery` in Compose.

`tests/ntfy-compose.e2e.yml` exercises the notify proxy directives with a real
nginx instance, including authenticated JSON/SSE subscriptions and attempted
`X-Forwarded-For` spoofing after the public rate limit has been exhausted. The
test uses HTTP inside isolated Docker networks; production TLS certificates and
the configuration actually installed on the server must be checked separately.


Reproduzierbarer IP-Integrationstest (alle vier Beispielproxies, HTTP ohne echte Zertifikate):

```sh
.venv/bin/python tests/create_proxy_fixture.py
docker compose -p cal11-proxy-check -f /tmp/cal11-proxy-check/compose.yml up --abort-on-container-exit --exit-code-from tester
docker compose -p cal11-proxy-check -f /tmp/cal11-proxy-check/compose.yml down -v
```

Die produktiven Proxyregeln werden für den Test übernommen; nur TLS und Backendziele
werden für das isolierte Netz angepasst. Geprüft werden Kalender, VP und der Notify-
Routingpfad mit echten HTTP-Anfragen, gefälschten Headern und untrusted Direktzugriffen.
Der eigentliche ntfy-Versand und seine ACLs werden separat durch `ntfy_end_to_end.py`
geprüft. Die installierte nginx-Konfiguration auf einem anderen Server ist damit
nicht automatisch aktualisiert oder geprüft.

Vertiefter nginx-Test mit echten Anmeldeprotokollen und Brute-Force-Sperren:

Voraussetzungen sind Linux mit Docker, freie Testports 39000–39003 und das freie
Subnetz `172.30.247.0/24`, Python mit PyYAML sowie das gebaute VP-Image
`jahrgangskalender-vp`. Der Test verwendet eine separate MariaDB mit Testkonten;
die Projektdatei `.env` wird in den Testcontainern ausgeblendet.

```sh
npm run build
.venv/bin/python tests/create_nginx_audit_fixture.py
docker compose -p cal11-nginx-audit -f /tmp/cal11-nginx-audit/compose.yml up -d
docker compose -p cal11-nginx-audit -f /tmp/cal11-nginx-audit/compose.yml exec -T client10 python /check/check.py
docker compose -p cal11-nginx-audit -f /tmp/cal11-nginx-audit/compose.yml exec -T client11 python /check/check.py
docker compose -p cal11-nginx-audit -f /tmp/cal11-nginx-audit/compose.yml exec -T client10 python /check/rate_limit.py blocked
docker compose -p cal11-nginx-audit -f /tmp/cal11-nginx-audit/compose.yml exec -T client11 python /check/rate_limit.py allowed
docker compose -p cal11-nginx-audit -f /tmp/cal11-nginx-audit/compose.yml exec -T nginx nginx -t
docker compose -p cal11-nginx-audit -f /tmp/cal11-nginx-audit/compose.yml logs --no-color ntfy
docker compose -p cal11-nginx-audit -f /tmp/cal11-nginx-audit/compose.yml down -v --timeout 1
```

Die Reihenfolge ist relevant; vor einer Wiederholung den Teststack mit `down -v`
entfernen. nginx läuft im Hostnetz und erreicht die Anwendungen über an
`127.0.0.1` gebundene Docker-Ports. Zwei Clients mit unterschiedlichen IPs prüfen
erfolgreiche und fehlgeschlagene Anmeldungen, sechs Varianten gefälschter Header,
die gespeicherten IPs in beiden Login-Tabellen sowie das nginx-Zugriffslog.
Zusätzlich werden die Kalender-Sperre nach acht Fehlversuchen und die VP-Sperre
nach fünf Fehlversuchen getestet: Auch eine korrekte PIN darf während der Sperre
keine Sitzung erzeugen; ein anderer Client muss sich am selben Konto anmelden
können. Die Sperren beziehen sich auf die Kombination Konto/IP, nicht auf eine
pauschale IP-Sperre über alle Konten. Die ntfy-JSON-Logs müssen für die Testaufrufe
`visitor_ip` mit `172.30.247.10` beziehungsweise `172.30.247.11` enthalten.

Dieser Test reproduziert den Host-nginx/Loopback/Docker-Pfad ohne TLS. Für den
Produktivbetrieb müssen die aktuelle Anwendung und Compose-Einstellungen sowie
die nginx-Headerregeln tatsächlich übernommen, Container neu erstellt und nginx
nach erfolgreichem `nginx -t` neu geladen werden. Ein zusätzlich vorgeschalteter
Proxy oder ein CDN wird durch diesen Aufbau nicht abgedeckt.
