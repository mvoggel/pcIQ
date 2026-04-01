"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface Props {
  rightSlot?: React.ReactNode;
}

export default function AppHeader({ rightSlot }: Props) {
  const pathname = usePathname();

  const navItems = [
    { href: "/signals", label: "Competitive Intel" },
    { href: "/cion", label: "CION Funds" },
  ];

  return (
    <header className="bg-slate-900 text-white">
      {/* Top row: logo + right slot */}
      <div className="px-4 sm:px-6 flex items-center justify-between py-3">
        <div className="flex items-center gap-2">
          <span className="text-lg font-bold tracking-tight">pcIQ</span>
          <span className="hidden sm:inline text-slate-500 text-sm">|</span>
          <span className="hidden sm:inline text-slate-400 text-sm">Private Credit Intelligence</span>
        </div>
        {rightSlot && (
          <div className="flex items-center gap-1">{rightSlot}</div>
        )}
      </div>

      {/* Bottom row: nav tabs */}
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
