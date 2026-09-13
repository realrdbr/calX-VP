import { useState } from 'react';
import InfoModal from './InfoModal';

export default function LegalLinks({ themeMode = 'system', className = '' }: { themeMode?: 'light' | 'dark' | 'system'; className?: string }) {
  const [infoOpen, setInfoOpen] = useState(false);
  return <>
    <nav aria-label="Informationen und Rechtliches" className={`legal-links ${className}`}>
      <button type="button" className="legal-link" onClick={() => setInfoOpen(true)}>Info</button>
      <a className="legal-link" href="/datenschutz">Datenschutzerklärung</a>
      <a className="legal-link" href="/impressum">Impressum</a>
    </nav>
    <InfoModal isOpen={infoOpen} onClose={() => setInfoOpen(false)} themeMode={themeMode} />
  </>;
}
