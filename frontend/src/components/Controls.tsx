import type { Lab } from "../hooks/use-lab.ts";

export function Controls({ lab }: { lab: Lab }) {
  return (
    <aside className="controls panel">
      <div className="section-label">1 / ELIGE UNA JUGADA</div>
      <h2>Elige dónde mirar.</h2>
      <label>
        Partido
        <select
          value={lab.matchId}
          disabled={!lab.matches.length || lab.loading}
          onChange={(e) => lab.setMatchId(Number(e.target.value))}
        >
          {!lab.matches.length && <option value="0">Conexión pendiente</option>}
          {lab.matches.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
      <div className="two-cols">
        <label>
          Período
          <select
            value={lab.period}
            onChange={(e) => lab.setPeriod(Number(e.target.value))}
          >
            <option value="1">Primer tiempo</option>
            <option value="2">Segundo tiempo</option>
          </select>
        </label>
        <label>
          Inicio (seg.)
          <input
            type="number"
            min="0"
            max="3600"
            step="1"
            value={lab.startSeconds}
            onChange={(e) => lab.setStartSeconds(Number(e.target.value))}
          />
        </label>
      </div>
      <label>
        Duración a cargar
        <select
          value={lab.durationSeconds}
          disabled={lab.loading}
          onChange={(e) => lab.setDurationSeconds(Number(e.target.value))}
        >
          <option value="900">15 minutos</option>
          <option value="1800">30 minutos</option>
          <option value="2700">Tiempo completo · hasta 45 minutos</option>
        </select>
      </label>
      <p className="small muted">
        El inicio equivale a {Math.floor(lab.startSeconds / 60)}:
        {String(lab.startSeconds % 60).padStart(2, "0")} de este tiempo.
      </p>
      <button
        className="button primary"
        disabled={!lab.matchId || lab.loading}
        onClick={() => void lab.load()}
      >
        {lab.loading
          ? `Cargando ${lab.durationSeconds / 60} min de Azure…`
          : `Cargar ${lab.durationSeconds / 60} minutos de partido ↗`}
      </button>
      <button
        className="text-button"
        onClick={() => void lab.connect()}
        disabled={lab.loading}
      >
        Reconectar al catálogo
      </button>
      {lab.error && (
        <div className="notice error" role="alert">
          {lab.error}
        </div>
      )}
      <div className="divider" />
      <div className="section-label">BLOQUE A ANALIZAR</div>
      <label>
        Equipo que defiende
        <select
          value={lab.automaticTeam ? "auto" : lab.teamId}
          disabled={!lab.episode}
          onChange={(e) =>
            e.target.value === "auto"
              ? lab.setAutomaticTeam(true)
              : lab.setTeamId(Number(e.target.value))
          }
        >
          <option value="auto">Automático · cercanía al balón</option>
          {lab.episode?.teams.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </label>
      <p className="small muted">
        Conexiones y anchuras calculadas automáticamente desde las posiciones.
        No hay distancia de conexión ni radio de cobertura elegidos a mano.
      </p>
      <label className="check">
        <input
          type="checkbox"
          checked={lab.flip}
          onChange={(e) => lab.setFlip(e.target.checked)}
        />
        Cambiar portería objetivo
      </label>
      <div className="divider" />
      <div className="scenario">
        <span className="section-label">EJEMPLO LOCAL · UNA SOLA JUGADA</span>
        <h3>Un bloque que se abre.</h3>
        <p>
          Ejemplo de geometría. Para ver múltiples jugadas, carga el partido de
          Azure.
        </p>
        <button className="button secondary" onClick={lab.demo}>
          Ver ejemplo geométrico local →
        </button>
      </div>
    </aside>
  );
}
