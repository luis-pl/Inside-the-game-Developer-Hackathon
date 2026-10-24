export interface Point {
  x: number;
  y: number;
}
export interface Player extends Point {
  id: number;
  teamId: number;
  number: number;
  name: string;
  goalkeeper: boolean;
}
export interface Frame {
  timeMs: number;
  ballInPlay: boolean;
  ball: Point | null;
  players: Player[];
}
export interface Team {
  id: number;
  name: string;
}
export interface Match {
  id: number;
  label: string;
  teams: Team[];
}
export interface Episode {
  window?: { startMs: number; endMs: number; sampleStepMs: number };
  frames: Frame[];
  teams: Team[];
  source: "azure" | "local";
  warnings: string[];
  matchLabel: string;
  period: number;
  homeAttacksRight: boolean;
  events: { timeMs: number; label: string }[];
  passes: CompletedPass[] | null;
}
export interface CompletedPass {
  id: string;
  source: number;
  target: number;
  teamId: number;
  timeMs: number;
}
export interface EpisodeQuery {
  durationSeconds?: number;
  matchId: number;
  period: number;
  startSeconds: number;
}
export interface EpisodeRepository {
  matches(signal?: AbortSignal): Promise<Match[]>;
  episode(query: EpisodeQuery, signal?: AbortSignal): Promise<Episode>;
}
export interface Bar {
  dimension: 0 | 1;
  birth: number;
  death: number | null;
}
export const PITCH = { length: 105, width: 68 } as const;
export const distance = (a: Point, b: Point) =>
  Math.hypot(a.x - b.x, a.y - b.y);
