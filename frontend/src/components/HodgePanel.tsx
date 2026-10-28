import type { Lab } from "../hooks/use-lab.ts";
import type { HodgeComponent } from "../domain/hodge/decomposition.ts";
import { HODGE_COLORS } from "./HodgeOverlay.tsx";
import "./hodge.css";

const PARTS = [
  {
    key: "gradient",
    name: "Potential",
    description: "Gradient flow; this does not measure progress towards goal.",
  },
  {
    key: "curl",
    name: "Local circulation",
    description: "Flow around the boundaries of filled triangles.",
  },
  {
    key: "harmonic",
    name: "Harmonic",
    description:
      "Flow with no divergence or local curl; depends on the complex.",
  },
] as const;
const percent = (value: number | null) =>
  value === null ? "—" : `${(value * 100).toFixed(1)} %`;

export function HodgePanel({ lab }: { lab: Lab }) {
  const h = lab.hodge,
    frame = lab.frame;
  const missing =
    h?.nodes.filter((id) => !frame?.players.some((p) => p.id === id)).length ??
    0;
  return (
    <section className="panel hodge-panel">
      <div className="hodge-header">
        <div>
          <div className="section-label">PASSING STRUCTURE</div>
          <h2>How the ball moves through the team.</h2>
        </div>
        <label>
          Passing complex
          <select
            aria-label="Passing complex"
            value={lab.complexMode}
            onChange={(e) =>
              lab.setComplexMode(e.target.value as "clique" | "graph")
            }
          >
            <option value="clique">Filled triangles</option>
            <option value="graph">Graph only</option>
          </select>
        </label>
      </div>
      {!lab.episode ? (
        <p className="muted small">
          Load a match window to analyse the completed-pass network.
        </p>
      ) : !h ? (
        <p className="notice error" role="status">
          Hodge analysis is unavailable because complete passing data is
          missing. This does not mean zero circulation.
        </p>
      ) : (
        <>
          <p className="small muted">
            Network aggregated over the loaded window (
            {Math.round(
              (lab.episode.frames.at(-1)!.timeMs -
                lab.episode.frames[0].timeMs +
                1000) /
                1000,
            )}{" "}
            s), not the current instant.{" "}
            {lab.removed !== null
              ? "Modified network: passes involving the removed player are excluded."
              : "Includes goalkeepers who participated in passes."}
          </p>
          <div className="hodge-facts">
            <span>
              <strong>{h.completedCount}</strong> completed passes
            </span>
            <span>
              <strong>{h.edges.length}</strong> interactions
            </span>
            <span>
              <strong>{h.triangles.length}</strong> triangles
            </span>
            <span>
              <strong>{h.firstBetti}</strong> H¹(ℝ) dimension
            </span>
          </div>
          <div className="hodge-parts">
            {PARTS.map((part) => (
              <article
                key={part.key}
                style={{ borderTopColor: HODGE_COLORS[part.key] }}
              >
                <span>{part.name}</span>
                <strong>{percent(h.fractions?.[part.key] ?? null)}</strong>
                <p>{part.description}</p>
              </article>
            ))}
          </div>
          <p className="small muted">
            Share of energy: ‖component‖² / ‖net flow‖². These values do not
            measure possession or effectiveness.
          </p>
          {!h.fractions && (
            <div className="notice">
              {h.completedCount
                ? "Passes in both directions balance out: net flow is zero."
                : "No completed passes are attributable to this team in the selected window."}{" "}
              Percentages are unavailable.
            </div>
          )}
          <div
            className="hodge-layer-buttons"
            aria-label="Hodge layer on the pitch"
          >
            <span>SHOW ON PITCH</span>
            {(
              [
                { key: "off", name: "Hidden" },
                { key: "net", name: "Net flow" },
                ...PARTS,
              ] as const
            ).map((part) => (
              <button
                key={part.key}
                type="button"
                aria-pressed={lab.hodgeLayer === part.key}
                onClick={() =>
                  lab.setHodgeLayer(part.key as HodgeComponent | "off")
                }
              >
                {part.name}
              </button>
            ))}
          </div>
          {missing > 0 && (
            <p className="small muted">
              {missing} network nodes are absent from this frame. Their edges
              are included in the calculation but are not drawn at invented
              positions.
            </p>
          )}
          <details className="hodge-method">
            <summary>Definitions & numerical checks</summary>
            <p>
              Canonical orientation by ID: fᵢⱼ = Nᵢ→ⱼ − Nⱼ→ᵢ. Unweighted
              Euclidean inner product. f = B₁ᵀφ + B₂ψ + h. The support retains
              pairs with balanced passes. Each triangle requires all three
              observed interactions; they need not occur in sequence.
            </p>
            <p>
              The harmonic component satisfies B₁h = 0 and B₂ᵀh = 0. Its space
              represents H¹ over real coefficients of the passing complex,
              distinct from spatial Rips H₁ over F₂. Gradient is not equivalent
              to progression; circulation is not equivalent to unproductive
              possession.
            </p>
            <p>
              Relative residuals: reconstruction{" "}
              {h.diagnostics.reconstruction.toExponential(1)}, harmonic
              divergence {h.diagnostics.harmonicDivergence.toExponential(1)},
              harmonic curl {h.diagnostics.harmonicCurl.toExponential(1)},
              orthogonality {h.diagnostics.orthogonality.toExponential(1)}.
            </p>
          </details>
          {!h.reliable && (
            <p role="alert" className="notice error">
              Numerical residuals exceed the tolerance. This decomposition is
              not displayed.
            </p>
          )}
        </>
      )}
    </section>
  );
}
