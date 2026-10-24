import { distance } from "./types.ts";
import type { Player } from "./types.ts";

export function connectivity(players: Player[], epsilon: number) {
  const edges: { a: Player; b: Player }[] = [];
  const adjacency = new Map(players.map((p) => [p.id, [] as number[]]));
  for (let i = 0; i < players.length; i++)
    for (let j = i + 1; j < players.length; j++) {
      if (distance(players[i], players[j]) <= epsilon) {
        edges.push({ a: players[i], b: players[j] });
        adjacency.get(players[i].id)!.push(players[j].id);
        adjacency.get(players[j].id)!.push(players[i].id);
      }
    }
  const groups: number[][] = [],
    visited = new Set<number>();
  for (const p of players) {
    if (visited.has(p.id)) continue;
    const group: number[] = [],
      stack = [p.id];
    visited.add(p.id);
    while (stack.length) {
      const id = stack.pop()!;
      group.push(id);
      for (const neighbor of adjacency.get(id)!)
        if (!visited.has(neighbor)) {
          visited.add(neighbor);
          stack.push(neighbor);
        }
    }
    groups.push(group);
  }
  return {
    groups,
    edges,
    largestFraction: players.length
      ? Math.max(...groups.map((g) => g.length)) / players.length
      : 0,
  };
}

export function removalImpacts(players: Player[], epsilon: number) {
  const before = connectivity(players, epsilon);
  return players
    .map((player) => {
      const after = connectivity(
        players.filter((p) => p.id !== player.id),
        epsilon,
      );
      return {
        player,
        components: after.groups.length,
        delta: after.groups.length - before.groups.length,
      };
    })
    .sort((a, b) => b.delta - a.delta || a.player.number - b.player.number);
}
