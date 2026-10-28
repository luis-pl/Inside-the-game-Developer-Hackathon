import { useEffect, useMemo, useRef, useState } from "react";
import { analyze } from "../domain/analysis.ts";
import type { Episode, EpisodeRepository, Match } from "../domain/types.ts";
import { localScenario } from "../data/local-scenario.ts";
import { analyzeTactics } from "../domain/tactics.ts";
import { persistence } from "../domain/persistence.ts";
import { interpolateFrame } from "../domain/interpolation.ts";
import { useReplayClock } from "./use-replay-clock.ts";
import { inferAttackingTeams } from "../domain/attacking-team.ts";
import { decomposePassingFlow } from "../domain/hodge/decomposition.ts";
import type { ComplexMode } from "../domain/hodge/passing-complex.ts";
import type { HodgeComponent } from "../domain/hodge/decomposition.ts";

export function useLab(repository: EpisodeRepository) {
  const [pitchView, setPitchView] = useState<"openings" | "block" | "passing">(
    "openings",
  );
  const [selectedOpening, setSelectedOpening] = useState("A1");
  const [complexMode, setComplexMode] = useState<ComplexMode>("clique");
  const [hodgeLayer, setHodgeLayer] = useState<HodgeComponent | "off">("off");
  const [matches, setMatches] = useState<Match[]>([]),
    [matchId, setMatchId] = useState(0);
  const [period, setPeriod] = useState(1),
    [startSeconds, setStartSeconds] = useState(0);
  const [durationSeconds, setDurationSeconds] = useState(300);
  const [episode, setEpisode] = useState<Episode | null>(null);
  const [manualTeamId, setManualTeamId] = useState(2);
  const [automaticTeam, setAutomaticTeam] = useState(true);
  const [removed, setRemovedState] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1),
    [flip, setFlip] = useState(false);
  const [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  const { playheadMs, seekTime, index, setIndex } = useReplayClock(
    episode,
    playing,
    speed,
    setPlaying,
  );
  const install = (value: Episode) => {
    setEpisode(value);
    setIndex(0);
    setRemovedState(null);
    setManualTeamId(value.teams[1].id);
    setAutomaticTeam(true);
    setPlaying(false);
    setFlip(false);
    setPitchView("openings");
    setHodgeLayer("off");
    setSelectedOpening("A1");
  };
  async function connect() {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError("");
    try {
      const rows = await repository.matches(controller.signal);
      if (!rows.length)
        throw new Error("No matches are available for this credential.");
      setMatches(rows);
      setMatchId(rows[0].id);
    } catch (e) {
      if (!controller.signal.aborted)
        setError(e instanceof Error ? e.message : "Connection failed.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }
  useEffect(() => {
    void connect();
    return () => request.current?.abort();
  }, [repository]); // repository is injected once at composition root
  async function load() {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError("");
    setPlaying(false);
    try {
      const value = await repository.episode(
        { matchId, period, startSeconds, durationSeconds },
        controller.signal,
      );
      if (!value.frames.length)
        throw new Error("The match window contains no frames.");
      install(value);
    } catch (e) {
      if (!controller.signal.aborted)
        setError(
          e instanceof Error ? e.message : "Could not load the match window.",
        );
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }
  const sampleFrame = episode?.frames[index] ?? null;
  const attackSelections = useMemo(
    () => (episode ? inferAttackingTeams(episode) : []),
    [episode],
  );
  const attackSelection = attackSelections[index];
  const teamId = automaticTeam
    ? (attackSelection?.defendingTeamId ?? manualTeamId)
    : manualTeamId;
  const frame = useMemo(
    () => (episode ? interpolateFrame(episode.frames, playheadMs) : null),
    [episode, playheadMs],
  );
  const effectiveRemoved = sampleFrame?.players.some(
    (p) => p.id === removed && p.teamId === teamId && !p.goalkeeper,
  )
    ? removed
    : null;
  const attackRight =
    !!episode &&
    (teamId === episode.teams[1].id
      ? episode.homeAttacksRight
      : !episode.homeAttacksRight) !== flip;
  const tacticalSeries = useMemo(
    () =>
      episode?.frames.map((f, i) => {
        const defending = automaticTeam
          ? attackSelections[i].defendingTeamId
          : manualTeamId;
        const right =
          (defending === episode.teams[1].id
            ? episode.homeAttacksRight
            : !episode.homeAttacksRight) !== flip;
        return analyzeTactics(f, defending, right, effectiveRemoved);
      }) ?? [],
    [
      episode,
      automaticTeam,
      attackSelections,
      manualTeamId,
      flip,
      effectiveRemoved,
    ],
  );
  const tactics = tacticalSeries[index] ?? null;
  // Legacy Rips comparison only: evaluate at its final finite H0 merge.
  // The match view uses the clearance filtration, never this scale.
  const epsilon = useMemo(
    () =>
      sampleFrame
        ? Math.max(
            0,
            ...persistence(
              sampleFrame.players.filter(
                (p) => p.teamId === teamId && !p.goalkeeper,
              ),
              126,
            )
              .filter((b) => b.dimension === 0 && b.death !== null)
              .map((b) => b.death!),
          )
        : 0,
    [sampleFrame, teamId],
  );
  const radius = 0;
  const analysis = useMemo(
    () =>
      sampleFrame
        ? analyze(
            sampleFrame,
            teamId,
            epsilon,
            radius,
            attackRight,
            effectiveRemoved,
          )
        : null,
    [sampleFrame, teamId, epsilon, radius, attackRight, effectiveRemoved],
  );
  const hodge = useMemo(
    () =>
      episode?.passes
        ? decomposePassingFlow(
            episode.passes,
            teamId,
            complexMode,
            effectiveRemoved,
          )
        : null,
    [episode, teamId, complexMode, effectiveRemoved],
  );
  const openingSeries = useMemo(
    () => tacticalSeries.map((t) => t.featured?.diameter ?? 0),
    [tacticalSeries],
  );
  const peakOpeningIndex = openingSeries.reduce(
    (best, value, i) => (value > (openingSeries[best] ?? 0) ? i : best),
    0,
  );
  return {
    durationSeconds,
    setDurationSeconds,
    automaticTeam,
    attackSelection,
    setAutomaticTeam: (value: boolean) => {
      setAutomaticTeam(value);
      setRemovedState(null);
    },
    playheadMs,
    seekTime,
    tacticalSeries,
    tactics,
    openingSeries,
    peakOpeningIndex,
    pitchView,
    setPitchView,
    selectedOpening,
    setSelectedOpening,
    goToOpening: () => {
      setPlaying(false);
      setIndex(peakOpeningIndex);
      setPitchView("openings");
      setHodgeLayer("off");
      setSelectedOpening("A1");
    },
    hodge,
    complexMode,
    setComplexMode,
    hodgeLayer,
    setHodgeLayer,
    matches,
    matchId,
    setMatchId,
    period,
    setPeriod,
    startSeconds,
    setStartSeconds,
    episode,
    index,
    setIndex,
    teamId,
    setTeamId: (id: number) => {
      setManualTeamId(id);
      setAutomaticTeam(false);
      setRemovedState(null);
    },
    removed: effectiveRemoved,
    setRemoved: (id: number | null) => {
      if (id !== null) {
        setManualTeamId(teamId);
        setAutomaticTeam(false);
      }
      setRemovedState(id);
    },
    epsilon,
    radius,
    playing,
    setPlaying,
    speed,
    setSpeed,
    flip,
    setFlip,
    loading,
    error,
    connect,
    load,
    frame,
    analysis,
    attackRight,
    demo: () => {
      request.current?.abort();
      setLoading(false);
      setError("");
      install(localScenario());
    },
  };
}
export type Lab = ReturnType<typeof useLab>;
