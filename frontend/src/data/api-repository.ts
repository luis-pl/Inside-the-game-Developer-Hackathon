import type {
  Episode,
  EpisodeQuery,
  EpisodeRepository,
  Match,
} from "../domain/types.ts";

async function read<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch("/dashboard-api/" + path, { signal });
  const body = await response.json();
  if (!response.ok)
    throw new Error(
      typeof body.error === "string"
        ? body.error
        : typeof body.error?.message === "string"
          ? body.error.message
          : "Could not reach the data server. Reconnect to the match catalogue or explore the local example.",
    );
  return body as T;
}

export class ApiEpisodeRepository implements EpisodeRepository {
  matches(signal?: AbortSignal) {
    return read<Match[]>("matches", signal);
  }
  episode(query: EpisodeQuery, signal?: AbortSignal) {
    const params = new URLSearchParams(
      Object.entries(query).map(([k, v]) => [k, String(v)]),
    );
    return read<Episode>("episode?" + params, signal);
  }
}
