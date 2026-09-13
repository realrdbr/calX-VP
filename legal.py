import json
import os
import re
from pathlib import Path
from html import escape


def render_legal_text(template: str, values: dict[str, str]) -> str:
    def substitute(match):
        value = values.get(match.group(1), "").strip() or "Vom Betreiber noch zu ergänzen"
        return value + ("." if match.group(2) and value[-1] not in ".!?…" else "")
    return re.sub(r"\{([A-Z_]+)\}(\.)?", substitute, template)


def legal_data():
    sections = json.loads((Path(__file__).parent / "public/privacy.json").read_text())
    defaults = json.loads((Path(__file__).parent / "public/legal-defaults.json").read_text())
    values = {key: os.getenv(key, "").strip() or value for key, value in defaults.items()}
    return [(title, render_legal_text(content, values)) for title, content in sections]


def render_legal_page(info=False, imprint=False):
    title = "Anbieterkennzeichnung gemäß § 5 DDG" if imprint else "Info" if info else "Datenschutzerklärung"
    if imprint:
        content = '<h2>Anbieter und Kontakt</h2><p>' + escape(os.getenv("PRIVACY_CONTROLLER", "Vom Betreiber noch zu ergänzen")) + '</p><p>' + escape(os.getenv("PRIVACY_ADDRESS", "Vom Betreiber noch zu ergänzen")) + '</p><p>E-Mail: ' + escape(os.getenv("SUPPORT_MAIL", "support@cal11.de")) + '</p><p>Die Projektsoftware steht unter der European Union Public Licence (EUPL) 1.2. Eingebundene Bibliotheken unterliegen ihren jeweiligen Lizenzen.</p><p>Privat betriebenes Kalender- und Vertretungsplanprojekt. Keine offizielle Verbindung mit dem Gymnasium Olbernhau.</p><p><a href="https://github.com/realrdbr/calX-VP" rel="noopener noreferrer">Quellcode auf GitHub</a></p>'
    elif info:
        content = '<p>Diese Webseite hat keine offizielle Verbindung mit dem Gymnasium Olbernhau und wurde privat von Schülern erstellt.</p><p>Der Zugriff ist für Schüler:innen der 11. Klasse des Gymnasiums Olbernhau sowie in Ausnahmefällen für weitere autorisierte Schüler:innen vorgesehen.</p>'
        content += '<p>Bei Fragen oder Problemen: ' + escape(os.getenv("SUPPORT_MAIL", "support@cal11.de")) + '</p><p><a href="https://github.com/realrdbr/calX-VP" rel="noopener noreferrer">Quellcode auf GitHub</a></p>'
    else:
        content = ''.join('<section><h2>' + escape(heading) + '</h2><p>' + escape(body) + '</p></section>' for heading, body in legal_data())
    return '<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + title + '</title><style>body{font:16px/1.6 system-ui;margin:0 auto;padding:24px;max-width:850px;color:#172033;background:#f8fafc}h2{font-size:1.2rem}a{color:#075985}footer{margin-top:32px;padding:20px;border-top:1px solid #cbd5e1}</style></head><body><main><a href="/">Zur Startseite</a><h1>' + title + '</h1>' + content + '</main></body></html>'
