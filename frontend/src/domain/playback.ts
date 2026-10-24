import type { Episode, Frame } from "./types.ts";

/** 1x means real time: one match second per screen second. */
export function advanceReplayTime(
  startMs: number,
  elapsedMs: number,
  speed: number,
  endMs: number,
) {
  return Math.min(endMs, startMs + Math.max(0, elapsedMs) * speed);
}

const ACTION_LABELS: Record<string, string> = {
  Pass: "Pase",
  Shot: "Tiro",
  Carry: "Conducción",
  Dribble: "Regate",
  Interception: "Intercepción",
  "Ball Recovery": "Recuperación",
};

export function episodeActions(episode: Episode | null) {
  return (episode?.events ?? [])
    .filter((event) => event.label in ACTION_LABELS)
    .map((event) => ({ ...event, displayLabel: ACTION_LABELS[event.label] }));
}

export function nextAction(episode: Episode | null, timeMs: number) {
  const actions = episodeActions(episode);
  return (
    actions.find((event) => event.timeMs > timeMs + 2000) ?? actions[0] ?? null
  );
}

/** Respect the sampled match clock; do not turn every frame into one second. */
export function frameDelayMs(
  frames: Frame[],
  index: number,
  speed: number,
): number | null {
  if (!Number.isFinite(speed) || speed <= 0)
    throw new RangeError("Invalid playback speed");
  const current = frames[index],
    next = frames[index + 1];
  if (!current || !next) return null;
  const gap = next.timeMs - current.timeMs;
  if (gap <= 0) throw new RangeError("Frames must have increasing timestamps");
  return gap / speed;
}

export function episodeTiming(episode: Episode | null) {
  const frames = episode?.frames ?? [];
  const sampleStepMs =
    episode?.window?.sampleStepMs ??
    (frames.length > 1 ? frames[1].timeMs - frames[0].timeMs : 1000);
  const startMs = episode?.window?.startMs ?? frames[0]?.timeMs ?? 0;
  const endMs =
    episode?.window?.endMs ??
    (frames.length ? frames.at(-1)!.timeMs + sampleStepMs : 2700000);
  return { sampleStepMs, startMs, endMs, durationMs: endMs - startMs };
}

export function durationLabel(ms: number): string {
  const seconds = Math.round(ms / 1000);
  return seconds % 60 === 0
    ? `${seconds / 60} min`
    : `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
}
