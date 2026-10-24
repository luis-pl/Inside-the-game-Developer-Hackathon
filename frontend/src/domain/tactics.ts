import type { Frame, Point } from "./types.ts";
import { distance } from "./types.ts";
import { findOpenings } from "./openings.ts";
import type { Opening } from "./openings.ts";
import { corridorClearance, isGabrielEdge } from "./corridors.ts";
import { spatialNetwork } from "./clearance-network.ts";
import type { SpatialNode, SpatialPath } from "./clearance-network.ts";

export interface ReachableOpening extends Opening {
  path: SpatialPath | null;
}

function pathToSpace(
  center: Point,
  network: ReturnType<typeof spatialNetwork>,
  defenders: Point[],
  sites: Point[],
): SpatialPath | null {
  let best: SpatialPath | null = null;
  for (const node of network.nodes) {
    const before = network.paths.get(node.id);
    if (!before) continue;
    const coincident = distance(node, center) < 1e-9;
    if (!coincident && !isGabrielEdge(node, center, sites)) continue;
    const clearance = Math.min(
      before.clearance,
      corridorClearance(node, center, defenders),
    );
    if (clearance <= 1e-9) continue;
    const candidate = {
      nodes: [...before.nodes, { ...center, id: "space" }],
      clearance,
      length: before.length + distance(node, center),
    };
    if (
      !best ||
      clearance > best.clearance ||
      (clearance === best.clearance && candidate.length < best.length)
    )
      best = candidate;
  }
  return best;
}

/** Selected team is the defending block; the other team supplies relay nodes.
 * Space vertices are terminal destinations, never artificial player relays.
 */
export function analyzeTactics(
  frame: Frame,
  defendingTeamId: number,
  attackRight: boolean,
  removed: number | null = null,
) {
  const players = frame.players.filter((p) => p.id !== removed);
  const defenders = players.filter((p) => p.teamId === defendingTeamId);
  const attackers = players.filter((p) => p.teamId !== defendingTeamId);
  const sourcePlayerId = frame.ball
    ? (attackers.find((p) => distance(p, frame.ball!) < 1e-9)?.id ?? null)
    : null;
  const nodes: SpatialNode[] = [];
  if (frame.ball) nodes.push({ ...frame.ball, id: "ball" });
  for (const player of attackers) {
    if (nodes.some((n) => distance(n, player) < 1e-9)) continue;
    nodes.push({ ...player, id: `player:${player.id}`, playerId: player.id });
  }
  const sites = [...players, ...(frame.ball ? [frame.ball] : [])];
  const network = spatialNetwork(nodes, defenders, sites);
  const openings: ReachableOpening[] = findOpenings(defenders, 0).map((o) => {
    const path = pathToSpace(o.center, network, defenders, sites);
    return { ...o, path, ballConnected: frame.ball ? path !== null : null };
  });
  const direction = attackRight ? 1 : -1;
  const progress = (point: Point) =>
    frame.ball ? direction * (point.x - frame.ball.x) : 0;
  const ranked = [...openings].sort(
    (a, b) =>
      Number(!!b.path) - Number(!!a.path) ||
      (b.path?.clearance ?? 0) - (a.path?.clearance ?? 0) ||
      progress(b.center) - progress(a.center) ||
      b.radius - a.radius,
  );
  const receivers = attackers
    .flatMap((player) => {
      const path = network.paths.get(`player:${player.id}`);
      return path ? [{ player, path, progress: progress(player) }] : [];
    })
    .sort(
      (a, b) =>
        b.path.clearance - a.path.clearance ||
        b.progress - a.progress ||
        a.path.length - b.path.length,
    );
  const forward = receivers.filter((r) => r.progress > 1e-9);
  return {
    sourcePlayerId,
    network,
    openings,
    featured: ranked[0] ?? null,
    receiver: forward[0] ?? receivers[0] ?? null,
    reachablePlayers: receivers.length,
    attackingTeamId: attackers[0]?.teamId ?? null,
  };
}
export type Tactics = ReturnType<typeof analyzeTactics>;
