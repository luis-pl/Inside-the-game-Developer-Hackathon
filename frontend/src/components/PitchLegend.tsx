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
    <div className="pitch-legend" aria-label="Leyenda de la cancha">
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
        Balón
      </span>
      {view === "openings" && (
        <>
          <span>
            <i className="legend-opening" />
            A1, A2…: espacio libre
          </span>
          <span>
            <i className="legend-route" />
            Camino al objetivo
          </span>
        </>
      )}
      {view === "block" && (
        <>
          <span>
            <i className="legend-group" />
            Mismo borde: mismo grupo
          </span>
          <span>
            <i className="legend-link" />
            Jugadores conectados
          </span>
        </>
      )}
      {view === "passing" && (
        <span>
          <i className="legend-arrow" />
          Sentido del flujo seleccionado
        </span>
      )}
    </div>
  );
}
