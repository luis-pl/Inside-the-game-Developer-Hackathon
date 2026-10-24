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
    throw new Error(body.error || "No se pudo consultar el servidor de datos.");
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
