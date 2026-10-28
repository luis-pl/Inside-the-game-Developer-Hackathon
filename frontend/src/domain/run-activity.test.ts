import test from "node:test";
import assert from "node:assert/strict";
import { runActivity } from "./run-activity.ts";

test("incomplete traces never imply a completed agent or zero usage", () => {
  const activity = runActivity({
    delegation: { action: "answer" },
    analysis: null,
  });
  assert.equal(activity.rows[0].status, "Question answered");
  assert.equal(activity.rows[1].status, "Not recorded");
  assert.equal(activity.rows[2].count, null);
  assert.equal(activity.elapsedMs, null);
  assert.doesNotThrow(() => runActivity(null));
});
test("partial retrieval keeps evidence and deduplicates reported errors", () => {
  const activity = runActivity({
    elapsed_ms: 3500,
    data: {
      status: "partial",
      evidence_catalog: [
        {
          evidence_id: "q1",
          operation: "get_shots",
          arguments: { match_id: 12 },
        },
      ],
      issues: [{ code: "TIMEOUT" }],
    },
    insights: { status: "partial", issues: ["TIMEOUT"] },
  });
  assert.equal(activity.rows[1].status, "Partial");
  assert.deepEqual(activity.evidence[0].arguments, { match_id: 12 });
  assert.deepEqual(activity.errors, ["TIMEOUT"]);
  assert.equal(activity.elapsedMs, 3500);
});
