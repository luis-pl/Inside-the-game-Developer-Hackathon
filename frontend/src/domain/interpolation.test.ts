import { test } from "node:test";
import assert from "node:assert/strict";
import { interpolateFrame, sampleIndexAt } from "./interpolation.ts";
import type { Frame, Player } from "./types.ts";

const player = (id: number, x: number): Player => ({
  id,
  teamId: 1,
  number: id,
  name: String(id),
  goalkeeper: false,
  x,
  y: 20,
});
const frames: Frame[] = [
  {
    timeMs: 600000,
    ballInPlay: true,
    ball: { x: 10, y: 30 },
    players: [player(1, 10), player(2, 20)],
  },
  {
    timeMs: 601000,
    ballInPlay: true,
    ball: { x: 20, y: 40 },
    players: [player(2, 30), player(1, 20)],
  },
];
test("fractional playback moves ball and players by identity without changing source samples", () => {
  const before = structuredClone(frames),
    midway = interpolateFrame(frames, 600250)!;
  assert.deepEqual(midway.ball, { x: 12.5, y: 32.5 });
  assert.deepEqual(
    midway.players.map((p) => [p.id, p.x]),
    [
      [1, 12.5],
      [2, 22.5],
    ],
  );
  assert.equal(sampleIndexAt(frames, 600999), 0);
  assert.equal(sampleIndexAt(frames, 601000), 1);
  assert.deepEqual(frames, before);
});
test("observations remain exact, with no extrapolation at either end", () => {
  assert.equal(interpolateFrame(frames, 600000), frames[0]);
  assert.equal(interpolateFrame(frames, 601000), frames[1]);
  assert.equal(interpolateFrame(frames, 900000), frames[1]);
  assert.equal(interpolateFrame(frames, 0), frames[0]);
  assert.equal(interpolateFrame([], 0), null);
});
test("gaps, stoppages, unavailable balls and substituted identities are not bridged", () => {
  assert.equal(
    interpolateFrame([frames[0], { ...frames[1], timeMs: 605000 }], 602500),
    frames[0],
  );
  assert.equal(
    interpolateFrame([frames[0], { ...frames[1], ballInPlay: false }], 600500)!
      .ball,
    frames[0].ball,
  );
  assert.equal(
    interpolateFrame([{ ...frames[0], ball: null }, frames[1]], 600500)!.ball,
    null,
  );
  const changed = { ...frames[1], players: [player(3, 80)] };
  assert.equal(
    interpolateFrame([frames[0], changed], 600500)!.players[0],
    frames[0].players[0],
  );
});
