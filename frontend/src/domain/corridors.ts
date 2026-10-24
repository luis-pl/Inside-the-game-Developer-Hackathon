import { distance, PITCH } from "./types.ts";
import type { Point } from "./types.ts";

const TOLERANCE = 1e-9;

export function distanceToSegment(p: Point, a: Point, b: Point): number {
  const dx = b.x - a.x,
    dy = b.y - a.y;
  const lengthSquared = dx * dx + dy * dy;
  const t =
    lengthSquared === 0
      ? 0
      : Math.max(
          0,
          Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / lengthSquared),
        );
  return Math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy);
}

/** Gabriel adjacency: the open disk with diameter ab contains no other site.
 * Numerical tolerance only; there is no sporting distance cutoff.
 */
export function isGabrielEdge(a: Point, b: Point, sites: Point[]): boolean {
  if (distance(a, b) <= TOLERANCE) return false;
  return !sites.some(
    (p) =>
      distance(p, a) > TOLERANCE &&
      distance(p, b) > TOLERANCE &&
      (p.x - a.x) * (p.x - b.x) + (p.y - a.y) * (p.y - b.y) < -TOLERANCE,
  );
}

/** Radius of the largest constant-width capsule around the segment that
 * avoids defender positions and stays within the pitch (including end caps).
 */
export function corridorClearance(
  a: Point,
  b: Point,
  defenders: Point[],
): number {
  return Math.max(
    0,
    Math.min(
      a.x,
      b.x,
      PITCH.length - a.x,
      PITCH.length - b.x,
      a.y,
      b.y,
      PITCH.width - a.y,
      PITCH.width - b.y,
      ...defenders.map((p) => distanceToSegment(p, a, b)),
    ),
  );
}
