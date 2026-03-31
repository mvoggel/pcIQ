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
    <header className="bg-slate-900 text-white px-6 py-0 flex items-stretch justify-between">
      {/* Left: logo + nav */}
      <div className="flex items-stretch gap-6">
        <div className="flex items-center gap-3 pr-6 border-r border-slate-700 my-3">
          <span className="text-lg font-bold tracking-tight">pcIQ</span>
          <span className="text-slate-500 text-sm">|</span>
          <span className="text-slate-400 text-sm">Private Credit Intelligence</span>
        </div>
        <nav className="flex items-stretch gap-1">
          {navItems.map(({ href, label }) => {
            const active = pathname === href || (href === "/signals" && pathname === "/");
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center px-4 text-sm font-medium border-b-2 transition-colors ${
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
      </div>

      {/* Right slot: day range picker or other controls */}
      {rightSlot && (
        <div className="flex items-center gap-1 py-3">{rightSlot}</div>
      )}
    </header>
  );
}
