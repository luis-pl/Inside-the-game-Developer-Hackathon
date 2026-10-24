import type {
  Episode,
  EpisodeQuery,
  EpisodeRepository,
  Match,
} from "../domain/types.ts";

/** Session-only LRU decorator. Store complete successful loads, never failures
 * or credentials. Playback and analysis use the same immutable episode object.
 */
export class MemoryEpisodeRepository implements EpisodeRepository {
  private readonly episodes = new Map<string, Episode>();
  private readonly source: EpisodeRepository;
  private readonly capacity: number;

  constructor(source: EpisodeRepository, capacity = 6) {
    if (!Number.isInteger(capacity) || capacity < 1)
      throw new RangeError("Invalid cache capacity");
    this.source = source;
    this.capacity = capacity;
  }

  matches(signal?: AbortSignal): Promise<Match[]> {
    return this.source.matches(signal);
  }

  async episode(query: EpisodeQuery, signal?: AbortSignal): Promise<Episode> {
    signal?.throwIfAborted();
    const key = `${query.matchId}:${query.period}:${query.startSeconds}:${query.durationSeconds ?? 2700}`;
    const cached = this.episodes.get(key);
    if (cached) {
      this.episodes.delete(key);
      this.episodes.set(key, cached);
      return cached;
    }
    const episode = await this.source.episode(query, signal);
    signal?.throwIfAborted();
    this.episodes.set(key, episode);
    if (this.episodes.size > this.capacity)
      this.episodes.delete(this.episodes.keys().next().value!);
    return episode;
  }
}
