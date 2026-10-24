import type { Opening } from "../domain/openings.ts";
export function OpeningOverlay({
  openings,
  selected,
}: {
  openings: Opening[];
  selected: string | null;
}) {
  return (
    <g
      className="opening-overlay"
      aria-label="Aperturas geométricas destacadas"
    >
      {openings.map((opening) => {
        const active = opening.id === selected,
          { x, y } = opening.center;
        return (
          <g key={opening.id}>
            <circle
              cx={x}
              cy={y}
              r={opening.radius}
              fill="#54e5cd"
              fillOpacity={active ? 0.25 : 0.1}
              stroke={active ? "#eafff6" : "#72d6c3"}
              strokeWidth={active ? 0.4 : 0.2}
              strokeDasharray={active ? undefined : ".9 .7"}
            />
            <line
              x1={x - opening.radius}
              y1={y}
              x2={x + opening.radius}
              y2={y}
              stroke="#bdfff0"
              strokeWidth=".16"
              strokeDasharray=".5 .6"
            />
            <rect
              x={x - 3.2}
              y={y - 2.1}
              width="6.4"
              height="4.2"
              rx="1"
              fill="#153e34"
              stroke="#91e9cf"
              strokeWidth=".12"
            />
            <text
              x={x}
              y={y - 0.3}
              textAnchor="middle"
              fill="#fff"
              fontWeight="800"
              fontSize="1.45"
            >
              {opening.id}
            </text>
            <text
              x={x}
              y={y + 1.3}
              textAnchor="middle"
              fill="#b2f4dc"
              fontSize="1.15"
            >
              {opening.diameter.toFixed(1)} m
            </text>
            <title>
              {opening.id}: círculo libre de {opening.diameter.toFixed(1)}{" "}
              metros de diámetro.{" "}
              {opening.ballConnected
                ? "Conectado con el balón en la malla."
                : "Sin conexión confirmada con el balón."}
            </title>
          </g>
        );
      })}
    </g>
  );
}
