import type { Lab } from "../hooks/use-lab.ts";

export function Controls({ lab }: { lab: Lab }) {
  return (
    <aside className="controls panel">
      <div className="section-label">01 / MATCH SETUP</div>
      <h2>Choose your focus.</h2>
      <label>
        Match
        <select
          value={lab.matchId}
          disabled={!lab.matches.length || lab.loading}
          onChange={(e) => lab.setMatchId(Number(e.target.value))}
        >
          {!lab.matches.length && (
            <option value="0">Waiting for connection</option>
          )}
          {lab.matches.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
      {lab.matches.length > 0 && (
        <p className="small muted">
          {lab.matches.length} matches{" "}
          {lab.matches.every((m) => m.dataKind?.startsWith("real_"))
            ? "recorded "
            : ""}
          available
        </p>
      )}
      <div className="two-cols">
        <label>
          Half
          <select
            value={lab.period}
            onChange={(e) => lab.setPeriod(Number(e.target.value))}
          >
            <option value="1">First half</option>
            <option value="2">Second half</option>
          </select>
        </label>
        <label>
          Start (seconds)
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
        Analysis window
        <select
          value={lab.durationSeconds}
          disabled={lab.loading}
          onChange={(e) => lab.setDurationSeconds(Number(e.target.value))}
        >
          <option value="60">1 minute · full detail</option>
          <option value="300">5 minutes · full detail</option>
          <option value="900">15 minutes</option>
          <option value="1800">30 minutes</option>
          <option value="2700">Full half · up to 45 minutes</option>
        </select>
      </label>
      <p className="small muted">
        Start time: {Math.floor(lab.startSeconds / 60)}:
        {String(lab.startSeconds % 60).padStart(2, "0")} into this half.
      </p>
      <button
        className="button primary"
        disabled={!lab.matchId || lab.loading}
        onClick={() => void lab.load()}
      >
        {lab.loading
          ? `Loading ${lab.durationSeconds / 60} min from Azure…`
          : `Load ${lab.durationSeconds / 60} minutes of match play ↗`}
      </button>
      <button
        className="text-button"
        onClick={() => void lab.connect()}
        disabled={lab.loading}
      >
        Reconnect to match catalogue
      </button>
      {lab.error && (
        <div className="notice error" role="alert">
          {lab.error}
        </div>
      )}
      <div className="divider" />
      <div className="section-label">DEFENDING TEAM</div>
      <label>
        Defending team
        <select
          value={lab.automaticTeam ? "auto" : lab.teamId}
          disabled={!lab.episode}
          onChange={(e) =>
            e.target.value === "auto"
              ? lab.setAutomaticTeam(true)
              : lab.setTeamId(Number(e.target.value))
          }
        >
          <option value="auto">Automatic · nearest to the ball</option>
          {lab.episode?.teams.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </label>
      <p className="small muted">
        Connections and corridor widths are calculated from player positions. No
        manually selected connection distance or coverage radius.
      </p>
      <label className="check">
        <input
          type="checkbox"
          checked={lab.flip}
          onChange={(e) => lab.setFlip(e.target.checked)}
        />
        Switch target goal
      </label>
      <div className="divider" />
      <div className="scenario">
        <span className="section-label">LOCAL DEMO · ONE SEQUENCE</span>
        <h3>Explore the geometry.</h3>
        <p>
          An illustrative geometric scenario. Load a match from Azure to explore
          recorded sequences.
        </p>
        <button className="button secondary" onClick={lab.demo}>
          Open local example →
        </button>
      </div>
    </aside>
  );
}
