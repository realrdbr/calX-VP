import { useEffect, useRef, useState } from 'react';
import info from '../../public/info.json';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  themeMode?: 'light' | 'dark' | 'system';
  required?: boolean;
  onAcknowledge?: () => Promise<void>;
}

export default function InfoModal({ isOpen, onClose, themeMode = 'system', required = false, onAcknowledge }: Props) {
  const [supportMail, setSupportMail] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    if (isOpen) {
      if (dialog.current && !dialog.current.open) dialog.current.showModal();
      fetch('/api/legal').then(r => { if (!r.ok) throw new Error(); return r.json(); })
        .then(data => setSupportMail(data.supportMail)).catch(() => setSupportMail('Kontakt derzeit nicht verfügbar'));
    } else if (dialog.current?.open) dialog.current.close();
  }, [isOpen]);
  const acknowledge = async () => {
    if (required && onAcknowledge) {
      setSaving(true);
      setError('');
      try { await onAcknowledge(); onClose(); }
      catch (reason) { setError(reason instanceof Error ? reason.message : 'Bestätigung konnte nicht gespeichert werden.'); }
      finally { setSaving(false); }
    } else onClose();
  };
  return <dialog ref={dialog} className="info-dialog" data-ui-theme={themeMode} aria-label="Info"
    onCancel={event => { if (required) event.preventDefault(); else onClose(); }} onClose={() => { if (!required) onClose(); }} onClick={event => { if (event.target === event.currentTarget && !required) onClose(); }}>
    <div className="info-head"><h2>Info</h2>{!required && <button type="button" className="info-close" onClick={onClose} aria-label="Schließen">✕</button>}</div>
    <div className="info-content">
      {info.paragraphs.map(paragraph => <p key={paragraph}>{paragraph}</p>)}
      <p>{info.supportPrefix} {supportMail || 'Kontakt wird geladen …'}.</p>
      <p><a href={info.repository} target="_blank" rel="noopener noreferrer">Quellcode auf GitHub</a></p>
      <p>{info.license}</p>
      <nav className="legal-links" aria-label="Rechtliches"><a className="legal-link" href="/datenschutz">Datenschutz</a><a className="legal-link" href="/impressum">Impressum</a></nav>
    </div>
    {error && <p role="alert" className="info-error">{error}</p>}
    <button type="button" className="info-submit" disabled={saving} onClick={() => void acknowledge()}>{saving ? 'Wird gespeichert …' : required ? 'Als gelesen markieren' : 'Schließen'}</button>
  </dialog>;
}
