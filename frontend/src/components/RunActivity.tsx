import { useState } from "react";
import { runActivity } from "../domain/run-activity.ts";
import { friendlyIssue } from "../domain/workspace-feedback.ts";

export function RunActivity({
  runs,
  busy,
}: {
  runs: unknown[];
  busy: boolean;
}) {
  const [offset, setOffset] = useState(0);
  const index = Math.max(0, runs.length - 1 - offset);
  const current = runActivity(runs[index]);
  return (
    <div className="run-activity">
      <div className="activity-heading">
        <div>
          <p className="workspace-eyebrow">BEHIND THE FINDINGS</p>
          <h2>Agent activity</h2>
        </div>
        {runs.length > 1 && (
          <label>
            Request
            <select
              value={Math.min(offset, runs.length - 1)}
              onChange={(e) => setOffset(Number(e.target.value))}
            >
              {runs.map((_, i) => (
                <option key={i} value={i}>
                  {i === 0
                    ? "Latest request"
                    : `${i} request${i > 1 ? "s" : ""} earlier`}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>
      {busy && (
        <p className="activity-notice" role="status">
          A request is running. Its recorded activity will appear when it
          finishes.
        </p>
      )}
      {!runs.length ? (
        <p>
          No completed activity yet. Ask a question to see how the agents use
          evidence.
        </p>
      ) : (
        <>
          <div className="activity-brief">
            <span>Your question</span>
            <p>{current.request || "Request text not recorded"}</p>
            {current.elapsedMs !== null && (
              <small>
                Recorded request time · {(current.elapsedMs / 1000).toFixed(1)}s
              </small>
            )}
          </div>
          <ol className="activity-agents">
            {current.rows.map((row, i) => (
              <li key={row.name}>
                <span className="activity-number">0{i + 1}</span>
                <div>
                  <div className="activity-row-title">
                    <h3>{row.name}</h3>
                    <span>{row.status}</span>
                  </div>
                  <p>{row.detail}</p>
                  {row.count && <strong>{row.count}</strong>}
                </div>
              </li>
            ))}
          </ol>
          <p className="activity-disclaimer">
            Only recorded activity is shown. A conversational answer may not
            require every agent.
          </p>
          {!!current.errors.length && (
            <section className="activity-issues" aria-label="Request issues">
              <h3>Needs attention</h3>
              {current.errors.map((code) => (
                <p key={code}>
                  {friendlyIssue(code)} <code>{code}</code>
                </p>
              ))}
            </section>
          )}
          {!!current.evidence.length && (
            <section className="activity-evidence">
              <h3>
                Evidence retrieved <span>{current.evidence.length}</span>
              </h3>
              <p>Each source links the analysis to a recorded data query.</p>
              {current.evidence.map((source, i) => (
                <details key={`${source.id}-${i}`}>
                  <summary>
                    {source.operation.replaceAll("_", " ")}{" "}
                    <small>{source.id}</small>
                  </summary>
                  <pre>{JSON.stringify(source.arguments, null, 2)}</pre>
                </details>
              ))}
            </section>
          )}
          <details className="activity-raw">
            <summary>Technical trace · request {index + 1}</summary>
            <pre>{JSON.stringify(runs[index], null, 2)}</pre>
          </details>
        </>
      )}
    </div>
  );
}
