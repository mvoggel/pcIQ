"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

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

export default function AppHeader({ rightSlot }: Props) {
  const pathname = usePathname();

  const navItems = [
    { href: "/signals",  label: "Funds"    },
    { href: "/advisors", label: "Advisors" },
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
