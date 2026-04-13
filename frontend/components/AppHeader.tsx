"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavTicker {
  ticker: string;
  nav: number | null;
  nav_change: number | null;
}

interface Props {
  rightSlot?: React.ReactNode;
  navTickers?: NavTicker[];
}

// Real logo PNG with CSS animation — preserves full brand detail
// while keeping the pulse/glow feel via filter + opacity keyframes
function AnimatedLogo() {
  return (
    <>
      <style>{`
        @keyframes pciq-logo-pulse {
          0%, 100% { opacity: 1;    filter: drop-shadow(0 0 4px rgba(99,179,237,0.0)); }
          50%       { opacity: 0.88; filter: drop-shadow(0 0 8px rgba(99,179,237,0.55)); }
        }
        .pciq-logo-anim {
          animation: pciq-logo-pulse 2.5s infinite ease-in-out;
        }
      `}</style>
      <Image
        src="/logo.png"
        alt="pcIQ"
        width={70}
        height={70}
        priority
        className="pciq-logo-anim rounded-full"
      />
    </>
  );
}

export default function AppHeader({ rightSlot, navTickers }: Props) {
  const pathname = usePathname();

  const navItems = [
    { href: "/advisors", label: "Advisors" },
    { href: "/signals",  label: "Funds"    },
    { href: "/cion",     label: "CION IQ"  },
  ];

  return (
    <header className="bg-slate-900 text-white">
      {/* Top row: logo + wordmark + right slot */}
      <div className="px-4 sm:px-6 flex items-center justify-between py-2">
        <div className="flex items-center gap-2.5">
          <AnimatedLogo />
          <span className="text-lg font-bold tracking-tight">pcIQ</span>
        </div>
        {rightSlot && (
          <div className="flex items-center gap-1">{rightSlot}</div>
        )}
      </div>

      {/* Nav tabs */}
      <nav className="flex items-end px-4 sm:px-6 gap-1">
        {navItems.map(({ href, label }) => {
          const active = pathname === href || (href === "/signals" && pathname === "/");
          return (
            <Link
              key={href}
              href={href}
              className={`px-3 sm:px-4 py-2.5 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                active
                  ? "border-blue-500 text-white"
                  : "border-transparent text-slate-400 hover:text-white hover:border-slate-500"
              }`}
            >
              {label}
            </Link>
          );
        })}
        {navTickers && navTickers.length > 0 && (
          <div className="ml-auto flex items-center gap-3 pb-2.5">
            {navTickers.map((t) => {
              const up = (t.nav_change ?? 0) >= 0;
              return (
                <span key={t.ticker} className="flex items-center gap-1">
                  <span className="text-xs text-slate-500 font-mono">{t.ticker}</span>
                  <span className={`text-xs font-semibold tabular-nums ${up ? "text-emerald-400" : "text-red-400"}`}>
                    {up ? "▲" : "▼"} {t.nav != null ? `$${t.nav.toFixed(2)}` : "—"}
                  </span>
                </span>
              );
            })}
          </div>
        )}
      </nav>
    </header>
  );
}
