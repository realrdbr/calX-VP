import info from '../../public/info.json';
import { useEffect, useState } from 'react';
import LegalLinks from '../components/LegalLinks';

export default function Legal({ imprint = false }: { imprint?: boolean }) {
  const [sections, setSections] = useState<string[][]>([]);
  const [contact, setContact] = useState({ controller: '', address: '', supportMail: '' });
  const [failed, setFailed] = useState(false);
  useEffect(() => { fetch('/api/legal').then(r => { if (!r.ok) throw new Error(); return r.json(); }).then(data => { setSections(data.sections); setContact(data); }).catch(() => setFailed(true)); }, []);
  return <main className="h-full overflow-y-auto max-w-3xl mx-auto p-6 space-y-6 leading-relaxed">
    <nav className="legal-links" aria-label="Zurück"><a className="legal-link" href="/">Zur Startseite</a></nav>
    <h1 className="text-2xl font-bold">{imprint ? 'Anbieterkennzeichnung gemäß § 5 DDG' : 'Datenschutzerklärung'}</h1>
    {imprint ? <>
      {failed ? <p>Die Anbieterangaben konnten nicht geladen werden. Bitte lade die Seite erneut.</p> : <>
        <section><h2 className="text-lg font-semibold">Anbieter und Kontakt</h2><p>{contact.controller}</p><p>{contact.address}</p><p>E-Mail: {contact.supportMail}</p></section>
        <p>{info.license}</p>
        <p>Privat betriebenes Kalender- und Vertretungsplanprojekt. Keine offizielle Verbindung mit dem Gymnasium Olbernhau.</p>
        <p><a className="underline" href="https://github.com/realrdbr/calX-VP" rel="noopener noreferrer">Quellcode auf GitHub</a></p>
      </>}
    </> : <>
      {failed && <p>Die Datenschutzerklärung konnte nicht geladen werden. Bitte lade die Seite erneut.</p>}
      {sections.map(([title, body]) => <section key={title}><h2 className="text-lg font-semibold mb-2">{title}</h2><p>{body}</p></section>)}
    </>}
    <footer className="border-t pt-5"><LegalLinks /></footer>
  </main>;
}
