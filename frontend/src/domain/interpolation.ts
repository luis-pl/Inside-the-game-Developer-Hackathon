import type { Frame, Point } from "./types.ts";

/** Last observed sample at or before time, using a binary lookup. */
export function sampleIndexAt(frames: Frame[], timeMs: number): number {
  let low = 0,
    high = frames.length - 1;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (frames[middle].timeMs <= timeMs) low = middle;
    else high = middle - 1;
  }
  return low;
}

const between = (a: Point, b: Point, fraction: number): Point => ({
  x: a.x + (b.x - a.x) * fraction,
  y: a.y + (b.y - a.y) * fraction,
});

/** Presentation only. Do not use interpolated positions for tactical metrics.
 * Hold gaps, missing identities and stoppage transitions rather than fabricate
 * observed samples or connect different players after a substitution.
 */
export function interpolateFrame(
  frames: Frame[],
  timeMs: number,
): Frame | null {
  const index = sampleIndexAt(frames, timeMs),
    a = frames[index],
    b = frames[index + 1];
  if (!a) return null;
  if (!b || timeMs <= a.timeMs) return a;
  const gap = b.timeMs - a.timeMs;
  if (gap <= 0 || gap > 1500) return a;
  const fraction = Math.min(1, (timeMs - a.timeMs) / gap);
  const nextPlayers = new Map(b.players.map((p) => [p.id, p]));
  return {
    ...a,
    timeMs,
    players: a.players.map((player) => {
      const next = nextPlayers.get(player.id);
      return next && next.teamId === player.teamId
        ? { ...player, ...between(player, next, fraction) }
        : player;
    }),
    ball:
      a.ball && b.ball && a.ballInPlay === b.ballInPlay
        ? between(a.ball, b.ball, fraction)
        : a.ball,
  };
}
