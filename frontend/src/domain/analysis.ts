import { connectivity, removalImpacts } from "./connectivity.ts";
import { freeSpace } from "./free-space.ts";
import { bettiAt, persistence } from "./persistence.ts";
import type { Frame } from "./types.ts";
import { findOpenings } from "./openings.ts";

export function analyze(
  frame: Frame,
  teamId: number,
  epsilon: number,
  radius: number,
  attackRight: boolean,
  removedId: number | null,
) {
  const baseline = frame.players.filter(
    (p) => p.teamId === teamId && !p.goalkeeper,
  );
  const selected = baseline.filter((p) => p.id !== removedId);
  const bars = persistence(selected);
  const defenders = frame.players.filter(
    (p) => p.teamId === teamId && p.id !== removedId,
  );
  const free = freeSpace(defenders, radius, frame.ball, attackRight);
  return {
    baseline: connectivity(baseline, epsilon),
    graph: connectivity(selected, epsilon),
    bars,
    h0: bettiAt(bars, 0, epsilon),
    h1: bettiAt(bars, 1, epsilon),
    removal: removalImpacts(baseline, epsilon),
    free,
    openings: findOpenings(defenders, radius, frame.ball, free.regionAt),
  };
}
export type Analysis = ReturnType<typeof analyze>;
