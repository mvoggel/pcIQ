"use client";

import Image from "next/image";
import Link from "next/link";
import { useState, useEffect } from "react";
import { usePathname } from "next/navigation";

interface FundTicker {
  ticker: string;
  nav: number | null;
  nav_change: number | null;
}

interface Props {
  rightSlot?: React.ReactNode;
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

function TickerBadge({ ticker, nav, nav_change }: FundTicker) {
  const up = (nav_change ?? 0) >= 0;
  return (
    <span className="inline-flex items-center gap-1.5 border border-slate-700 rounded-md px-2.5 py-1 bg-slate-800/60">
      <span className="text-[10px] font-mono text-slate-400 leading-none">
        {ticker}
      </span>
      <span
        className={`text-xs font-semibold tabular-nums leading-none ${
          up ? "text-emerald-400" : "text-red-400"
        }`}
      >
        {up ? "▲" : "▼"}&thinsp;{nav != null ? `$${nav.toFixed(2)}` : "—"}
      </span>
    </span>
  );
}

export default function AppHeader({ rightSlot }: Props) {
  const pathname = usePathname();
  const [tickers, setTickers] = useState<FundTicker[]>([]);

  useEffect(() => {
    const base = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    fetch(`${base}/api/cion/funds`, { next: { revalidate: 300 } })
      .then((r) => r.json())
      .then((funds: Array<{ ticker: string; nav: number | null; nav_change: number | null; error?: string }>) => {
        setTickers(
          funds
            .filter((f) => !f.error && f.nav != null)
            .map((f) => ({ ticker: f.ticker, nav: f.nav, nav_change: f.nav_change }))
        );
      })
      .catch(() => {/* silent — tickers simply don't appear */});
  }, []);

  const navItems = [
    { href: "/advisors", label: "Advisors" },
    { href: "/signals",  label: "Funds"    },
    { href: "/cion",     label: "CION IQ"  },
  ];

  return (
    <header className="bg-slate-900 text-white">
      {/* Top row: logo · wordmark · [tickers] · rightSlot */}
      <div className="px-4 sm:px-6 flex items-center justify-between py-2">
        {/* Left: logo + wordmark */}
        <div className="flex items-center gap-2.5">
          <AnimatedLogo />
          <span className="text-lg font-bold tracking-tight">pcIQ</span>
        </div>

        {/* Right: live CION tickers + optional caller slot */}
        <div className="flex items-center gap-2">
          {tickers.map((t) => (
            <TickerBadge key={t.ticker} {...t} />
          ))}
          {rightSlot && (
            <div className="flex items-center gap-1 ml-1">{rightSlot}</div>
          )}
        </div>
      </div>

      {/* Nav tabs */}
      <nav className="flex px-4 sm:px-6 gap-1">
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
      </nav>
    </header>
  );
}
