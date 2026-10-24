import type { Episode, Frame } from "./types.ts";

export interface AttackSelection {
  attackingTeamId: number;
  defendingTeamId: number;
  nearestPlayerId: number | null;
  reason: "nearest" | "held" | "tie";
}

/** Explicit positional estimate, not recorded possession. Keep the preceding
 * selection during missing-ball samples, stoppages or an inter-team tie.
 */
export function inferAttackingTeams(episode: Episode): AttackSelection[] {
  const teamIds = episode.teams.map((t) => t.id);
  let attackingTeamId = teamIds[0];
  return episode.frames.map((frame: Frame) => {
    let nearestPlayerId: number | null = null;
    let reason: AttackSelection["reason"] = "held";
    if (frame.ball && frame.ballInPlay) {
      const ranked = frame.players
        .filter((p) => teamIds.includes(p.teamId))
        .map((p) => ({
          player: p,
          distance: Math.hypot(p.x - frame.ball!.x, p.y - frame.ball!.y),
        }))
        .sort((a, b) => a.distance - b.distance || a.player.id - b.player.id);
      const nearest = ranked[0];
      if (nearest) {
        const tied = ranked.some(
          (p) =>
            p.player.teamId !== nearest.player.teamId &&
            Math.abs(p.distance - nearest.distance) < 1e-9,
        );
        reason = tied ? "tie" : "nearest";
        if (!tied) {
          attackingTeamId = nearest.player.teamId;
          nearestPlayerId = nearest.player.id;
        }
      }
    }
    return {
      attackingTeamId,
      defendingTeamId: teamIds.find((id) => id !== attackingTeamId)!,
      nearestPlayerId,
      reason,
    };
  });
}
