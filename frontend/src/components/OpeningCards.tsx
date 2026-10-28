import type { Opening } from "../domain/openings.ts";
export function OpeningCards({
  openings,
  selected,
  onSelect,
}: {
  openings: Opening[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="opening-cards">
      {openings.length ? (
        openings.map((opening) => (
          <button
            key={opening.id}
            className={selected === opening.id ? "active" : ""}
            aria-pressed={selected === opening.id}
            onClick={() => onSelect(opening.id)}
          >
            <span className="opening-number">{opening.id}</span>
            <span>
              <strong>{opening.diameter.toFixed(1)} m of space</strong>
              <small>
                {opening.ballConnected === null
                  ? "Ball connection unknown"
                  : opening.ballConnected
                    ? "Connected to the ball"
                    : "Not connected to the ball"}
              </small>
            </span>
            <span className="opening-status">
              {opening.ballConnected ? "↗" : "○"}
            </span>
          </button>
        ))
      ) : (
        <p className="small muted">
          No empty circles with radius at least 1 m are detected within the
          block at this setting. Space may exist outside the block.
        </p>
      )}
      <p className="opening-help">
        Each circle fits without touching coverage zones. Size is its diameter.
        Up to three spaces are highlighted; labels are recalculated at each
        sample.
      </p>
    </div>
  );
}
