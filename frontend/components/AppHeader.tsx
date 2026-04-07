"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface Props {
  rightSlot?: React.ReactNode;
}

// Animated SVG logo rendered inline so CSS keyframe animations run in the browser.
// An <img> or next/image src would strip the <style> block and kill the animations.
function AnimatedLogo() {
  return (
    <svg width="70" height="70" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <style>{`
          .pciq-pulse {
            animation: pciq-pulse 2.5s infinite ease-in-out;
            transform-origin: 50px 50px;
          }
          .pciq-glow {
            animation: pciq-glow 2s infinite ease-in-out;
          }
          @keyframes pciq-pulse {
            0%, 100% { transform: scale(1);    opacity: 1;    }
            50%       { transform: scale(1.05); opacity: 0.85; }
          }
          @keyframes pciq-glow {
            0%, 100% { opacity: 1;   }
            50%       { opacity: 0.6; }
          }
        `}</style>
      </defs>

      {/* Background circle */}
      <circle cx="50" cy="50" r="48" fill="#0F2A44"/>

      {/* Brain outline */}
      <g stroke="white" strokeWidth="2.5" fill="none" className="pciq-pulse">
        <path d="M30 50 C30 30, 45 30, 50 40 C55 30, 70 30, 70 50
                 C70 70, 55 70, 50 60 C45 70, 30 70, 30 50 Z"/>
      </g>

      {/* Nodes */}
      <g fill="white" className="pciq-glow">
        <circle cx="35" cy="45" r="2"/>
        <circle cx="65" cy="45" r="2"/>
        <circle cx="40" cy="60" r="2"/>
        <circle cx="60" cy="60" r="2"/>
      </g>

      {/* Lightbulb */}
      <g stroke="white" strokeWidth="2.5" fill="none" className="pciq-glow">
        <path d="M50 35 C45 35, 43 40, 43 43 C43 48, 47 50, 50 50
                 C53 50, 57 48, 57 43 C57 40, 55 35, 50 35 Z"/>
        <line x1="47" y1="52" x2="53" y2="52"/>
        <line x1="48" y1="55" x2="52" y2="55"/>
      </g>
    </svg>
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
        <div className="flex items-end gap-2.5">
          <AnimatedLogo />
          <span className="text-lg font-bold tracking-tight mb-1">pcIQ</span>
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
