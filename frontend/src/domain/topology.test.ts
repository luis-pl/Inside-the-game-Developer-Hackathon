import { test } from "node:test";
import assert from "node:assert/strict";
import { persistence, bettiAt } from "./persistence.ts";
import { connectivity, removalImpacts } from "./connectivity.ts";
import { freeSpace } from "./free-space.ts";
import type { Player } from "./types.ts";

test("square has one H1 class between side and diagonal; filled triangle has none", () => {
  const square = persistence([
    { x: 0, y: 0 },
    { x: 10, y: 0 },
    { x: 10, y: 10 },
    { x: 0, y: 10 },
  ]);
  assert.equal(bettiAt(square, 1, 11), 1);
  assert.equal(bettiAt(square, 1, 15), 0);
  assert.equal(
    bettiAt(
      persistence([
        { x: 0, y: 0 },
        { x: 10, y: 0 },
        { x: 5, y: 8 },
      ]),
      1,
      11,
    ),
    0,
  );
});
test("unmerged components are censored at cutoff, not assigned a finite death", () => {
  assert.equal(
    persistence([
      { x: 0, y: 0 },
      { x: 100, y: 0 },
    ]).filter((b) => b.death === null).length,
    2,
  );
  assert.equal(bettiAt(persistence([]), 0, 15), 0);
});
const player = (id: number, x: number): Player => ({
  id,
  x,
  y: 34,
  teamId: 1,
  name: `P${id}`,
  number: id,
  goalkeeper: false,
});
test("removing the bridge splits the graph and leaves inputs unchanged", () => {
  const players = [player(1, 0), player(2, 10), player(3, 20)];
  assert.equal(connectivity(players, 11).groups.length, 1);
  assert.equal(removalImpacts(players, 11)[0].player.id, 2);
  assert.equal(players.length, 3);
});
test("wall spanning touchlines prevents route; opening wall restores it", () => {
  const wall = Array.from({ length: 24 }, (_, i) => ({ x: 50, y: i * 3 }));
  assert.equal(freeSpace(wall, 2, { x: 10, y: 34 }, true).reachable, false);
  assert.equal(freeSpace([], 2, { x: 10, y: 34 }, true).reachable, true);
  assert.equal(
    freeSpace([{ x: 10, y: 34 }], 2, { x: 10, y: 34 }, true).startCovered,
    true,
  );
});
test("persistence invariant under translation and player permutation", () => {
  const points = [
    { x: 0, y: 0 },
    { x: 10, y: 0 },
    { x: 10, y: 10 },
    { x: 0, y: 10 },
  ];
  const summarize = (p: typeof points) =>
    persistence(p)
      .map((b) => JSON.stringify(b))
      .sort();
  assert.deepEqual(
    summarize(points),
    summarize(points.map((p) => ({ x: p.x + 20, y: p.y + 15 })).reverse()),
  );
});
