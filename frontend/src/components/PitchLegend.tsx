export type PitchView = "openings" | "block" | "passing";
export function PitchLegend({
  view,
  teamName,
  rivalName,
}: {
  view: PitchView;
  teamName: string;
  rivalName: string;
}) {
  return (
    <div className="pitch-legend" aria-label="Pitch legend">
      <span>
        <i className="legend-player defender" />
        Bloque: {teamName}
      </span>
      <span>
        <i className="legend-player attacker" />
        Rival: {rivalName}
      </span>
      <span>
        <i className="legend-ball" />
        Ball
      </span>
      {view === "openings" && (
        <>
          <span>
            <i className="legend-opening" />
            A1, A2…: open space
          </span>
          <span>
            <i className="legend-route" />
            Path to target
          </span>
        </>
      )}
      {view === "block" && (
        <>
          <span>
            <i className="legend-group" />
            Same outline: same group
          </span>
          <span>
            <i className="legend-link" />
            Connected players
          </span>
        </>
      )}
      {view === "passing" && (
        <span>
          <i className="legend-arrow" />
          Selected flow direction
        </span>
      )}
    </div>
  );
}
