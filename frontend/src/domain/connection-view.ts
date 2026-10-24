import type { Frame, Point } from "./types.ts";
import type { SpatialNode } from "./clearance-network.ts";
import type { Tactics } from "./tactics.ts";

export function projectNode(
  node: SpatialNode,
  frame: Frame,
): SpatialNode | null {
  const point =
    node.id === "ball"
      ? frame.ball
      : node.playerId !== undefined
        ? frame.players.find((p) => p.id === node.playerId)
        : node;
  return point ? { ...node, x: point.x, y: point.y } : null;
}

/** Present existing graph edges; never invent links merely to fill the screen. */
export function connectionView(tactics: Tactics, frame: Frame) {
  const { network } = tactics;
  const edges = network.edges.flatMap((edge) => {
    const a = projectNode(edge.a, frame),
      b = projectNode(edge.b, frame);
    if (!a || !b) return [];
    const connected =
      network.paths.has(edge.a.id) && network.paths.has(edge.b.id);
    const kind = !connected
      ? "separate"
      : edge.a.id === "ball" || edge.b.id === "ball"
        ? "direct"
        : "relay";
    return [{ ...edge, a, b, kind }];
  });
  const nodes = frame.players
    .filter((p) => p.teamId === tactics.attackingTeamId)
    .map((player) => {
      const node = network.nodes.find((n) => n.playerId === player.id);
      const path = node ? network.paths.get(node.id) : null;
      const source = tactics.sourcePlayerId === player.id;
      const kind = source
        ? "source"
        : !path
          ? "separate"
          : path.nodes.length === 2
            ? "direct"
            : "relay";
      return { player, kind };
    });
  return {
    edges,
    nodes,
    connected: nodes.filter((n) => n.kind !== "separate").length,
    direct: nodes.filter((n) => n.kind === "direct").length,
    total: nodes.length,
  };
}

export const connectionPoints = (points: Point[]) =>
  points.map((p) => `${p.x},${p.y}`).join(" ");
