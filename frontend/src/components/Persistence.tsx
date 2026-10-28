import type { Bar } from "../domain/types.ts";

export function Persistence({
  bars,
  epsilon,
}: {
  bars: Bar[];
  epsilon?: number;
}) {
  const visible = bars.filter((b) => b.dimension === 1);
  return (
    <div className="persistence-chart">
      <div className="scale">
        <span>0 m</span>
        <span>20</span>
        <span>40 m</span>
      </div>
      <div className="bars" aria-label="H1 persistence intervals">
        {epsilon !== undefined && (
          <div
            className="scale-marker"
            style={{ left: `${(epsilon / 40) * 100}%` }}
          />
        )}
        {visible.length ? (
          visible.map((bar, i) => (
            <div key={i} className="bar-row">
              <div
                className="bar"
                title={`Birth ${bar.birth.toFixed(2)} m; ${bar.death === null ? "censored at 40 m" : "death " + bar.death.toFixed(2) + " m"}`}
                style={{
                  left: `${(bar.birth / 40) * 100}%`,
                  width: `${(((bar.death ?? 40) - bar.birth) / 40) * 100}%`,
                }}
              >
                {bar.death === null ? "→" : ""}
              </div>
            </div>
          ))
        ) : (
          <p className="muted small">
            No H₁ cycles with positive persistence in this frame.
          </p>
        )}
      </div>
      <p className="small muted">
        Rips · F₂ · truncated at 40 m. Persistence measures distance, not time.
        A cycle alone does not define a tactical space.
      </p>
    </div>
  );
}
