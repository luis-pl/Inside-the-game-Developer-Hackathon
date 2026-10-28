/** Bounded browser calls; a lost connection must not look like endless work. */
export async function workspaceApi(
  path: string,
  options: RequestInit = {},
  timeoutMs = path === "chat-catalog" ? 60_000 : 12_000,
  fetcher: typeof fetch = fetch,
) {
  const deadline = AbortSignal.timeout(timeoutMs);
  const signal = options.signal
    ? AbortSignal.any([options.signal, deadline])
    : deadline;
  try {
    const result = await fetcher("/workspace-api/" + path, {
      credentials: "same-origin",
      ...options,
      signal,
      headers: {
        "Content-Type": "application/json",
        "X-Inside-Game": "workspace",
        ...options.headers,
      },
    });
    if (!result.ok) {
      const body = await result.json().catch(() => ({}));
      throw new Error(body.error?.code ?? `HTTP_${result.status}`);
    }
    return await result.json();
  } catch (error) {
    if (deadline.aborted && !options.signal?.aborted)
      throw new Error("REQUEST_TIMEOUT");
    throw error;
  }
}

/** One request in flight; stop on failure until the user reconnects explicitly. */
export function watchConversation<T>(
  load: (signal: AbortSignal) => Promise<T>,
  onState: (state: T) => boolean,
  onError: (error: unknown) => void,
  intervalMs = 2500,
) {
  let active = true;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const controller = new AbortController();
  const tick = async () => {
    try {
      const state = await load(controller.signal);
      if (active && onState(state)) timer = setTimeout(tick, intervalMs);
    } catch (error) {
      if (active) onError(error);
    }
  };
  void tick();
  return () => {
    active = false;
    clearTimeout(timer);
    controller.abort();
  };
}
