interface Props {
  territories: string[];
  active: string;
  onChange: (territory: string) => void;
}

export default function TerritoryTabs({ territories, active, onChange }: Props) {
  return (
    <div className="bg-white border-b border-slate-200">
      <nav className="flex gap-1 overflow-x-auto scrollbar-none px-4 sm:px-6">
        {territories.map((t) => (
          <button
            key={t}
            onClick={() => onChange(t)}
            className={`px-3 sm:px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              active === t
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-slate-500 hover:text-slate-800 hover:border-slate-300"
            }`}
          >
            {t}
          </button>
        ))}
      </nav>
    </div>
  );
}
