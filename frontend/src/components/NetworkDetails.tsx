import type { Lab } from "../hooks/use-lab.ts";
import { Persistence } from "./Persistence.tsx";
import { episodeTiming } from "../domain/playback.ts";

export function NetworkDetails({ lab }: { lab: Lab }) {
  const network = lab.tactics?.network;
  return (
    <section className="network-details">
      <h2>Reading the attacking network</h2>
      <p>
        Green rings and lines identify attackers connected to the ball, directly
        or through teammates. Grey dashed lines connect attackers without a path
        to the ball. The counter includes all connected attackers; direct
        connections count only the ball's immediate neighbours. Yellow
        highlights the chain towards the selected space.
      </p>
      <p>
        Automatic mode estimates the attacking team from the player nearest to
        the ball in each original sample. The previous team is retained during
        stoppages, missing ball positions or tied distances. This is not
        confirmed possession. Team colours remain consistent when roles change.
        You can select the defending team manually.
      </p>
      <h2>How connections are calculated</h2>
      <p>
        Nodes represent the ball and attacking players. Two nodes connect when
        the disc with their segment as its diameter contains no other player or
        ball: a Gabriel graph of all positions, restricted to attacking nodes. A
        defender inside that disc prevents the connection. No maximum connection
        distance is selected.
      </p>
      <p>
        For each edge, the minimum distance from every defender to the segment
        is calculated and limited by pitch boundaries. Twice this value is the
        corridor width clear of defensive positions. A defender on the segment
        gives zero width and removes the edge.
      </p>
      <h3>Topology of available space</h3>
      <p>
        The H₀ filtration adds edges from greatest to smallest clearance.
        Kruskal's algorithm produces a maximum spanning forest, preserving the
        widest bottleneck of any chain between the ball and each teammate in
        this graph. All critical values are considered, without a selected
        threshold. Chains show potential geometric connections, not completed
        passes.
      </p>
      {network && (
        <>
          <p>
            <b>{network.nodes.length}</b> nodes · <b>{network.edges.length}</b>{" "}
            connections · <b>{network.components}</b> final components.
          </p>
          <table>
            <caption>H₀ merges · corridor width in metres</caption>
            <thead>
              <tr>
                <th>Critical width</th>
                <th>Remaining components</th>
              </tr>
            </thead>
            <tbody>
              {network.merges.map((m, i) => (
                <tr key={i}>
                  <td>{(2 * m.clearance).toFixed(2)} m</td>
                  <td>{m.components}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <h3>Spaces between defenders</h3>
      <p>
        Candidate centres are Voronoi vertices of three defenders inside the
        outfield players' convex hull. Goalkeepers and pitch boundaries also
        limit the space. Up to three separated candidates with radius ≥ 1 m are
        retained. This display filter does not determine connections.
      </p>
      <p>
        Each space is a terminal destination, never an intermediate player. The
        chain from the ball maximises its narrowest corridor. Connected spaces
        are prioritised, then clearance, progress and size. Space size is the
        circle diameter, not the chain width.
      </p>
      <h3>Model scope</h3>
      <p>
        Defenders are point positions. No control radius, speed or reaction time
        is assumed. Clear means empty in this snapshot, not safe from
        interception. The Gabriel graph is conservative: a missing connection
        does not prove that a pass or route is impossible.{" "}
        {lab.episode?.dataKind?.startsWith("real_")
          ? `Real data with masked identities from ${lab.episode.provider ?? "the stated provider"},`
          : "Synthetic demonstration data,"}{" "}
        with observations sampled every{" "}
        {episodeTiming(lab.episode).sampleStepMs / 1000} seconds. Animation
        interpolates positions between adjacent samples for display. Topological
        calculations use original samples only. Gaps and absent identities are
        not interpolated. The clock replays a recorded window; it is not a live
        broadcast.
      </p>
      <h3>Block signature · Rips persistence</h3>
      <p>
        An independent diagnostic across scales up to 40 m, over F₂. Its H₁
        cycles are not the circles on the pitch and do not determine match
        connections.
      </p>
      {lab.analysis && <Persistence bars={lab.analysis.bars} />}
      <details className="node-comparison">
        <summary>Compare by removing a defender</summary>
        <p>
          A geometric comparison, not a substitution or prediction of other
          players' movement.
        </p>
        <div className="node-buttons">
          {lab.frame?.players
            .filter((p) => p.teamId === lab.teamId && !p.goalkeeper)
            .map((p) => (
              <button
                key={p.id}
                aria-pressed={lab.removed === p.id}
                onClick={() =>
                  lab.setRemoved(lab.removed === p.id ? null : p.id)
                }
              >
                #{p.number} · {p.name}
              </button>
            ))}
        </div>
        {lab.removed !== null && (
          <button onClick={() => lab.setRemoved(null)}>
            Restore full defensive block
          </button>
        )}
      </details>
    </section>
  );
}
