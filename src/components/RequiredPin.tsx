import LegalLinks from './LegalLinks';
import { UserPreferences } from '../types';
import { FormEvent, useState } from 'react';

export default function RequiredPin({ preferences }: { preferences: UserPreferences }) {
  const [pin, setPin] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    if (!/^\d{4}$/.test(pin) || pin !== confirm) { setError('Bitte gib zweimal dieselbe vierstellige PIN ein.'); return; }
    setBusy(true); setError('');
    try {
      const response = await fetch('/api/pin', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin, pinConfirm: confirm }) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || 'Speichern fehlgeschlagen.');
      window.location.reload();
    } catch (error) { setError(error instanceof Error ? error.message : 'Speichern fehlgeschlagen.'); setBusy(false); }
  }
  return <main className="required-pin-page" data-ui-theme={preferences.themeMode || (preferences.darkMode ? 'dark' : 'system')}>
    <form onSubmit={submit} className="required-pin-card" aria-labelledby="pin-title">
      <h1 id="pin-title" className="text-xl font-bold">Persönliche PIN festlegen</h1>
      <p role="alert">Bevor du Kalender oder Vertretungsplan weiter nutzt, musst du eine persönliche vierstellige PIN festlegen.</p>
      <label className="block">Neue PIN<input autoFocus required type="password" inputMode="numeric" pattern="[0-9]{4}" minLength={4} maxLength={4} autoComplete="new-password" value={pin} onChange={e => setPin(e.target.value.replace(/[^0-9]/g, '').slice(0, 4))} className="block border rounded p-2 w-full" /></label>
      <label className="block">PIN wiederholen<input required type="password" inputMode="numeric" pattern="[0-9]{4}" minLength={4} maxLength={4} autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value.replace(/[^0-9]/g, '').slice(0, 4))} className="block border rounded p-2 w-full" /></label>
      {error && <p role="alert" className="pin-error">{error}</p>}
      <button disabled={busy} className="pin-save">{busy ? 'Wird gespeichert …' : 'PIN sicher speichern'}</button>
      <LegalLinks themeMode={preferences.themeMode || (preferences.darkMode ? 'dark' : 'system')} />
      <button type="button" className="mt-3 text-sm underline underline-offset-4" onClick={async () => { await fetch('/api/logout', { method: 'POST' }); window.location.href = '/'; }}>Abmelden</button>
    </form>
  </main>;
}
