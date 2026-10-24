import { test } from "node:test";
import assert from "node:assert/strict";
import { persistence, bettiAt } from "./persistence.ts";
import { connectivity } from "./connectivity.ts";
import type { Player } from "./types.ts";

test("H0 agrees with independent graph traversal over multiple scales", () => {
  const players: Player[] = Array.from({ length: 10 }, (_, i) => ({
    id: i,
    teamId: 1,
    number: i + 1,
    name: `P${i}`,
    goalkeeper: false,
    x: (i * 17) % 80,
    y: (i * i * 7) % 60,
  }));
  const bars = persistence(players);
  for (const scale of [5, 10, 15, 20, 25, 30])
    assert.equal(
      bettiAt(bars, 0, scale),
      connectivity(players, scale).groups.length,
    );
});

test("dilating geometry dilates positive persistence intervals", () => {
  const points = [
    { x: 0, y: 0 },
    { x: 6, y: 0 },
    { x: 6, y: 6 },
    { x: 0, y: 6 },
  ];
  const a = persistence(points).filter((b) => b.dimension === 1);
  const b = persistence(points.map((p) => ({ x: p.x * 2, y: p.y * 2 }))).filter(
    (b) => b.dimension === 1,
  );
  assert.equal(b[0].birth, a[0].birth * 2);
  assert.equal(b[0].death, a[0].death! * 2);
});
