type Props = { seconds: number };

export default function LoginLockNotice({ seconds }: Props) {
  if (seconds <= 0) return null;
  const countdown = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;

  return (
    <div
      className="rounded-xl border border-[#f48fb1] bg-[#fce4ec] px-3.5 py-3 text-center text-sm font-semibold text-[#ad1457] dark:border-[#8e3b59] dark:bg-[#351420] dark:text-[#ff8bb3]"
      role="status"
      aria-live="polite"
    >
      Zu viele Anmeldungen, versuche es in <span className="font-extrabold tabular-nums">{countdown}</span> erneut
    </div>
  );
}
