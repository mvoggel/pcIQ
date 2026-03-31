const KNOWN = ["icapital", "cais", "altigo", "moonfare"];

function isKnown(name: string) {
  const lower = name.toLowerCase();
  return KNOWN.some((p) => lower.includes(p));
}

interface Props {
  platformCounts: Record<string, number>;
}

export default function PlatformPanel({ platformCounts }: Props) {
  const sorted = Object.entries(platformCounts).sort(([, a], [, b]) => b - a);

  return (
    <div className="w-44 shrink-0">
      <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2">
        Platform Activity
      </h2>
      <div className="border border-blue-200 rounded-lg p-3 max-h-72 overflow-y-auto">
        {sorted.length === 0 ? (
          <p className="text-xs text-slate-400">No platform data this period.</p>
        ) : (
          <ul className="space-y-1.5">
            {sorted.map(([name, count]) => {
              const known = isKnown(name);
              return (
                <li key={name} className="flex items-center justify-between gap-2">
                  <span
                    className={`text-xs truncate ${
                      known ? "text-slate-800 font-medium" : "text-slate-500"
                    }`}
                    title={name}
                  >
                    {known && (
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500 mr-1.5 shrink-0 align-middle" />
                    )}
                    {name}
                  </span>
                  <span className="text-xs text-slate-400 shrink-0 tabular-nums">
                    {count}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      <p className="text-xs text-slate-400 mt-2">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-500 mr-1 align-middle" />
        Known platform
      </p>
    </div>
  );
}
