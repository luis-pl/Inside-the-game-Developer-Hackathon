import { useEffect } from "react";
import type { CSSProperties } from "react";
import type { Lab } from "../hooks/use-lab.ts";
import { Pitch } from "./Pitch.tsx";
import { MatchPlayback, matchClock } from "./MatchPlayback.tsx";
import "./match-view.css";
import { episodeTiming, durationLabel } from "../domain/playback.ts";
import { connectionView } from "../domain/connection-view.ts";

export function FieldPanel({ lab }: { lab: Lab }) {
  const { frame, episode, analysis, tactics } = lab;
  const timing = episodeTiming(episode);
  useEffect(() => {
    if (episode) window.scrollTo({ top: 0, behavior: "instant" });
  }, [episode]);
  const defending = episode?.teams.find((t) => t.id === lab.teamId);
  const attacking = episode?.teams.find((t) => t.id !== lab.teamId);
  const leftTeam = episode?.teams[0] ?? defending;
  const rightTeam = episode?.teams[1] ?? attacking;
  const teamRole = (id: number | undefined, fallback: string) =>
    !episode
      ? fallback
      : id === lab.teamId
        ? "DEFENDING"
        : lab.automaticTeam
          ? "ESTIMATED ATTACK"
          : "ATTACKING";
  const view = lab.hodgeLayer !== "off" ? "passing" : lab.pitchView;
  const path = tactics?.featured?.path ?? tactics?.receiver?.path;
  const connections = tactics && frame ? connectionView(tactics, frame) : null;
  const teamColor = (id?: number) =>
    id === episode?.teams[1].id ? "#91dcc4" : "#e6b779";
  const choose = (next: typeof lab.pitchView) => {
    lab.setPitchView(next);
    lab.setHodgeLayer(next === "passing" ? "net" : "off");
  };
  return (
    <section className="match-screen" id="pitch-analysis">
      <div className="match-scoreboard">
        <div className="match-teams">
          <span
            className="defending-team"
            style={{ "--team-color": teamColor(leftTeam?.id) } as CSSProperties}
          >
            {leftTeam?.name ?? "Defence"}
            <small>{teamRole(leftTeam?.id, "DEFENDING")}</small>
          </span>
          <span className="match-versus">vs</span>
          <span
            className="attacking-team"
            style={
              { "--team-color": teamColor(rightTeam?.id) } as CSSProperties
            }
          >
            {rightTeam?.name ?? "Attack"}
            <small>{teamRole(rightTeam?.id, "ESTIMATED ATTACK")}</small>
          </span>
        </div>
        <div className="match-clock">
          <span>H{episode?.period ?? 1}</span>
          <strong>{frame ? matchClock(frame.timeMs) : "00:00"}</strong>
        </div>
        <span className={`play-state ${lab.playing ? "running" : ""}`}>
          {lab.playing ? "● PLAYING" : "Ⅱ PAUSED"}
        </span>
      </div>
      <div className="match-signals" aria-live="off">
        {view === "openings" ? (
          <>
            <span className="space-signal">
              <i />
              {tactics?.featured ? (
                <>
                  Open space <b>{tactics.featured.diameter.toFixed(0)} m</b>
                </>
              ) : (
                "No highlighted space"
              )}
            </span>
            <span className="attacker-signal">
              <i />
              Connected to ball{" "}
              <b>
                {frame?.ball && connections
                  ? `${connections.connected}/${connections.total}`
                  : "—"}
              </b>
              {frame?.ball && connections && (
                <small>{connections.direct} direct</small>
              )}
            </span>
            <span className="connection-signal">
              <i />
              {!frame?.ball ? (
                "Ball position unavailable"
              ) : path ? (
                <>
                  Clear corridor <b>{(2 * path.clearance).toFixed(1)} m</b>
                </>
              ) : (
                "No connection from the ball"
              )}
            </span>
          </>
        ) : view === "block" ? (
          <span>
            GEOMETRIC NETWORK · {tactics?.network.edges.length ?? 0} connections
            · {tactics?.reachablePlayers ?? 0} teammates connected to the ball
          </span>
        ) : (
          <span>
            PASSES BY {defending?.name} · FULL WINDOW · aggregated, not the
            current instant
          </span>
        )}
        {frame && !frame.ballInPlay && (
          <span className="stopped-ball">BALL OUT OF PLAY</span>
        )}
        {lab.removed !== null && (
          <button
            className="simulation-flag"
            onClick={() => lab.setRemoved(null)}
          >
            PLAYER REMOVAL SIMULATION · RESTORE ↺
          </button>
        )}
      </div>
      <div className="match-pitch">
        {frame && analysis && tactics ? (
          <Pitch
            frame={frame}
            analysis={analysis}
            tactics={tactics}
            broadcast={true}
            teamId={lab.teamId}
            mintTeamId={episode?.teams[1].id}
            removed={lab.removed}
            radius={0}
            coverage={false}
            spaces={false}
            connections={view === "block"}
            route={false}
            attackRight={lab.attackRight}
            onRemove={lab.setRemoved}
            hodge={lab.hodge}
            hodgeLayer={lab.hodgeLayer}
            showOpenings={false}
            selectedOpening={null}
            view={view}
          />
        ) : (
          <div className="match-empty">
            <h1>See the shape behind the game.</h1>
            <button
              className="button mint"
              disabled={lab.loading || !lab.matchId}
              onClick={() => void lab.load()}
            >
              {lab.loading
                ? "Connecting to Azure…"
                : `▶ Load ${lab.durationSeconds / 60} minutes of match play`}
            </button>
            <a href="#match-settings">Match settings ↓</a>
          </div>
        )}
      </div>
      <MatchPlayback lab={lab} />
      <div className="match-source">
        <span>
          {episode?.source === "azure"
            ? episode.dataKind === "real_pseudonymized"
              ? "SKILLCORNER · REAL, PSEUDONYMISED · AZURE"
              : episode.dataKind === "real_anonymized"
                ? "METRICA SPORTS · REAL, ANONYMISED · AZURE"
                : "AZURE · SYNTHETIC DATA"
            : episode
              ? "LOCAL GEOMETRIC EXAMPLE"
              : "NO DATA LOADED"}{" "}
          · {(episode?.frames.length ?? 0).toLocaleString("en-GB")} SAMPLES ·{" "}
          {1000 / timing.sampleStepMs} Hz
        </span>
        <span>
          WINDOW: {durationLabel(timing.durationMs)} ·{" "}
          {matchClock(timing.startMs)}–{matchClock(timing.endMs)}
          {" · "}1× = REAL TIME
        </span>
      </div>
      <div className="match-layers" aria-label="Pitch layer">
        <span>View</span>
        <button
          aria-pressed={view === "openings"}
          onClick={() => choose("openings")}
        >
          Space & connections
        </button>
        <button aria-pressed={view === "block"} onClick={() => choose("block")}>
          Full network
        </button>
        <button
          aria-pressed={view === "passing"}
          onClick={() => choose("passing")}
        >
          Aggregated passes
        </button>
      </div>
    </section>
  );
}
