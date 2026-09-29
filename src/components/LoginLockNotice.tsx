import { ShieldAlert } from 'lucide-react';

type Props = { seconds: number };

export default function LoginLockNotice({ seconds }: Props) {
  if (seconds <= 0) return null;
  const minutes = Math.ceil(seconds / 60);

  return (
    <div
      className="mt-3 flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-rose-950 dark:border-rose-900/70 dark:bg-rose-950/40 dark:text-rose-100"
      role="status"
      aria-live="polite"
    >
        <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-rose-100 text-rose-600 dark:bg-rose-900/70 dark:text-rose-200">
        <ShieldAlert className="h-4 w-4" aria-hidden="true" />
      </span>
      <span className="min-w-0">
        <span className="block text-sm font-bold">Anmeldung für diese IP gesperrt</span>
        <span className="mt-0.5 block text-xs leading-relaxed text-rose-800 dark:text-rose-200">
          Erneut möglich in <span className="font-bold tabular-nums">{minutes} Minuten</span>.
        </span>
      </span>
    </div>
  );
}
