import test from "node:test";
import assert from "node:assert/strict";
import { chartSegments, nearestSample } from "./chart-series.ts";
test("tracking gaps and missing values are not rendered as continuous evidence", () => {
  const samples = [
    { timeMs: 0, value: 0 },
    { timeMs: 200, value: 3 },
    { timeMs: 400, value: null },
    { timeMs: 600, value: 4 },
    { timeMs: 3000, value: 2 },
  ];
  assert.deepEqual(
    chartSegments(samples, 300).map((s) => s.map((p) => p.timeMs)),
    [[0, 200], [600], [3000]],
  );
  assert.equal(chartSegments(samples, 300)[0][0].value, 0);
});
test("chart selection uses actual timestamps including irregular sample spacing", () => {
  const samples = [
    { timeMs: 10000, value: 2 },
    { timeMs: 10200, value: 5 },
    { timeMs: 14000, value: 3 },
  ];
  assert.equal(nearestSample(samples, 10170), 1);
  assert.equal(nearestSample(samples, 13700), 2);
  assert.equal(nearestSample(samples, -1), 0);
  assert.equal(nearestSample(samples, 90000), 2);
  assert.equal(nearestSample([], 100), -1);
});
