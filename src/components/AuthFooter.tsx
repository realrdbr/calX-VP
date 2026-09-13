import LegalLinks from './LegalLinks';
import { KALENDER_URL } from '../lib/externalLinks';

export default function AuthFooter() {

  return (
    <>
      <footer className="fixed inset-x-0 bottom-0 z-40 border-t border-[#cbd5e1] dark:border-[#333] py-4 bg-white dark:bg-[#121212]">
        <div className="w-full px-6 sm:px-12 flex items-center justify-between text-[13.5px] font-semibold text-[#0f172a] dark:text-[#eee]">
          <LegalLinks />

          <a href={KALENDER_URL} className="font-bold tracking-wide">
            cal11.de
          </a>
        </div>
      </footer>

    </>
  );
}
