import test from "node:test";
import assert from "node:assert/strict";
import {
  changeLabel,
  changedIds,
  clampPanel,
  friendlyIssue,
  reportLinkLabel,
} from "./workspace-feedback.ts";

test("update targets identify changed graphs without accepting executable selector content", () => {
  const changes = {
    revision: 4,
    added: [
      { id: "xg", title: "xG", insight_id: "xg_story" },
      { id: "</script>", title: "unsafe", insight_id: "xg_story" },
    ],
    updated: [{ id: "xg", title: "xG", insight_id: "xg_story" }],
    removed: [],
    title_changed: false,
    analysis_updated: true,
  };
  assert.deepEqual(changedIds(changes), ["xg"]);
  assert.match(changeLabel(changes), /charts added/);
  assert.equal(
    changeLabel({ ...changes, added: [], updated: [], title_changed: true }),
    "Title updated",
  );
});
test("panel sizes respect usable document space and persistable integer bounds", () => {
  assert.equal(clampPanel(900, 900, "chat"), 610);
  assert.equal(clampPanel(-10, 900, "chat"), 250);
  assert.equal(clampPanel(NaN, 1400, "history"), 170);
  assert.equal(clampPanel(1000, 1400, "history"), 300);
  assert.equal(clampPanel(350.4, 900, "chat"), 350);
});
test("an Insights timeout is explained as latency rather than missing data", () => {
  assert.match(friendlyIssue("INSIGHTS_TIMEOUT"), /longer than expected/);
  assert.doesNotMatch(friendlyIssue("INSIGHTS_TIMEOUT"), /no data/);
  assert.match(friendlyIssue("DATA_EVIDENCE_UNAVAILABLE"), /evidence/);
});

test("a conversational explanation does not claim the report was updated", () => {
  assert.equal(
    reportLinkLabel([{ delegation: { action: "answer" } }]),
    "View report",
  );
  assert.equal(
    reportLinkLabel([{ delegation: { action: "modify" } }]),
    "View update",
  );
});
