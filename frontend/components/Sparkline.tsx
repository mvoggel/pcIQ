interface Props {
  data: number[];
  width?: number;
  height?: number;
}

export default function Sparkline({ data, width = 240, height = 56 }: Props) {
  if (data.length < 2) return null;

  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pad = 2;

  const points = data.map((val, i) => {
    const x = pad + (i / (data.length - 1)) * (width - pad * 2);
    const y = pad + (1 - (val - min) / range) * (height - pad * 2);
    return [x, y] as [number, number];
  });

  const pathD =
    "M " + points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" L ");

  // Fill path: close back to baseline
  const fillD =
    pathD +
    ` L ${points[points.length - 1][0].toFixed(1)},${height} L ${points[0][0].toFixed(1)},${height} Z`;

  const isUp = data[data.length - 1] >= data[0];
  const stroke = isUp ? "#10b981" : "#ef4444";
  const fill = isUp ? "rgba(16,185,129,0.08)" : "rgba(239,68,68,0.08)";

  return (
    <svg
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="block"
    >
      {/* Area fill */}
      <path d={fillD} fill={fill} />
      {/* Line */}
      <path d={pathD} fill="none" stroke={stroke} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      {/* End dot */}
      <circle
        cx={points[points.length - 1][0]}
        cy={points[points.length - 1][1]}
        r={2.5}
        fill={stroke}
      />
    </svg>
  );
}
