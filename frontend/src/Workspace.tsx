import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import "./workspace.css";

type Match = {
  match_id: number;
  home_team_name: string;
  away_team_name: string;
  is_synthetic?: boolean;
  data_kind?: string;
};
type Context = {
  match_ids?: number[];
  team_ids?: number[];
  player_ids?: number[];
  scope?: unknown;
};
type Conversation = {
  id: string;
  title: string;
  messages: { role: string; content: string; error?: string }[];
  context: Context;
  busy: boolean;
  stage: string;
  report: null | {
    report_id: string;
    revision: number;
    blocks: unknown[];
    status: string;
  };
  runs: unknown[];
};
type Summary = { id: string; title: string; busy: boolean };
const stages: Record<string, string> = {
  queued: "Solicitud en cola",
  catalog: "Consultando partidos",
  interpreting: "Entendiendo tu solicitud",
  data: "Data está recuperando la evidencia",
  analysis: "Analista e Insights están trabajando",
  editing: "Actualizando la página",
  partial: "Informe con resultados parciales",
  complete: "Informe listo",
  clarification: "Necesito un detalle más",
  error: "La ejecución se interrumpió",
};

async function api(path: string, options: RequestInit = {}) {
  const result = await fetch("/workspace-api/" + path, {
    credentials: "same-origin",
    ...options,
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
  return result.json();
}
function Icon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    plus: "M12 5v14M5 12h14",
    chat: "M5 4h14v12H9l-4 4V4Z",
    sun: "M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
    moon: "M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z",
    send: "m5 12 7-7 7 7M12 5v15",
    download: "M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4",
    file: "M6 3h8l4 4v14H6V3Zm8 0v5h4M9 12h6m-6 4h6",
    logout: "M9 4H4v16h5m5-13 5 5-5 5m-6-5h11",
    menu: "M4 6h16M4 12h16M4 18h16",
    arrow: "M5 12h14m-5-5 5 5-5 5",
    close: "m6 6 12 12M6 18 18 6",
  };
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] ?? paths.file} />
    </svg>
  );
}
function download(text: string, name: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
function documentHtml(html: string, dark: boolean) {
  const policy = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'">`;
  const theme = dark
    ? `<style>:root{--ink:#ebebeb;--muted:#aaa;--line:#353535;--paper:#181818;color-scheme:dark}body,header,main,footer,section.insight{background:#181818!important;color:#ebebeb!important}h1,h2,h3,dt,dd,p,summary{color:inherit}figure svg,.pitch{background:#242824!important}figcaption,.method,.palette-note{color:#aaa}a{color:#ccc}button,select{background:#292929;color:#eee;border-color:#555}pre{background:#242424;color:#ddd}.field-lines{stroke:#8b9c90}figure svg text:not(.jersey){fill:#ccc}.status{background:#2b3a2e;color:#d4e0d6}</style>`
    : "";
  return html
    .replace(/<head>/i, "<head>" + policy)
    .replace("</head>", theme + "</head>");
}

export function Workspace() {
  const [mobile, setMobile] = useState(
    () => matchMedia("(max-width:760px)").matches,
  );
  const [theme, setTheme] = useState(
    () => localStorage.getItem("inside-game-theme") ?? "dark",
  );
  const [auth, setAuth] = useState(false),
    [local, setLocal] = useState(false),
    [key, setKey] = useState("");
  const [sessions, setSessions] = useState<Summary[]>([]),
    [conversation, setConversation] = useState<Conversation | null>(null);
  const [matches, setMatches] = useState<Match[]>([]),
    [match, setMatch] = useState("");
  const [text, setText] = useState(""),
    [html, setHtml] = useState(""),
    [error, setError] = useState("");
  const [loading, setLoading] = useState(false),
    [catalogLoading, setCatalogLoading] = useState(false);
  const [pane, setPane] = useState("document"),
    [view, setView] = useState("report"),
    [sidebar, setSidebar] = useState(false);
  const active = useRef<string | null>(null),
    end = useRef<HTMLDivElement>(null),
    input = useRef<HTMLTextAreaElement>(null);
  const drawer = useRef<HTMLElement>(null),
    menuButton = useRef<HTMLButtonElement>(null),
    closeButton = useRef<HTMLButtonElement>(null),
    wasOpen = useRef(false);
  useEffect(() => {
    const mq = matchMedia("(max-width:760px)");
    const changed = () => {
      setMobile(mq.matches);
      setSidebar(false);
    };
    mq.addEventListener("change", changed);
    return () => mq.removeEventListener("change", changed);
  }, []);
  useEffect(() => {
    if (mobile && sidebar) closeButton.current?.focus();
    else if (mobile && wasOpen.current) menuButton.current?.focus();
    wasOpen.current = sidebar;
    if (!mobile || !sidebar) return;
    const handle = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setSidebar(false);
        return;
      }
      if (event.key !== "Tab") return;
      const nodes = drawer.current?.querySelectorAll<HTMLElement>(
        "a[href],button:not([disabled]),select,textarea,input",
      );
      if (!nodes?.length) return;
      const first = nodes[0],
        last = nodes[nodes.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handle);
    return () => document.removeEventListener("keydown", handle);
  }, [mobile, sidebar]);
  useEffect(() => {
    localStorage.setItem("inside-game-theme", theme);
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  useEffect(() => {
    api("config").then((c) => setLocal(c.local_demo));
    api("conversations")
      .then((rows) => {
        setAuth(true);
        setSessions(rows);
      })
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (!auth) return;
    setCatalogLoading(true);
    api("chat-catalog")
      .then((d) => setMatches(d.matches))
      .catch(() =>
        setError("No pude cargar los partidos. Pulsa «Recargar partidos»."),
      )
      .finally(() => setCatalogLoading(false));
  }, [auth]);
  useEffect(() => {
    end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [conversation?.messages.length, conversation?.stage]);
  useEffect(() => {
    if (!conversation?.busy) return;
    const id = conversation.id;
    const timer = setInterval(
      () =>
        api("conversations/" + id)
          .then((c) => {
            if (active.current === id) setConversation(c);
            if (!c.busy) api("conversations").then(setSessions);
          })
          .catch(() =>
            setError(
              "Se perdió la conexión. Vuelve a abrir la conversación para recuperar su estado.",
            ),
          ),
      2500,
    );
    return () => clearInterval(timer);
  }, [conversation?.id, conversation?.busy]);
  useEffect(() => {
    setHtml("");
    if (!conversation?.report) return;
    const id = conversation.id;
    fetch("/workspace-api/conversations/" + id + "/page", {
      credentials: "same-origin",
    })
      .then(async (r) => {
        if (!r.ok) throw Error();
        const h = await r.text();
        if (active.current === id) setHtml(h);
      })
      .catch(() =>
        setError("El informe ya no está disponible. Puedes generar uno nuevo."),
      );
  }, [
    conversation?.id,
    conversation?.report?.report_id,
    conversation?.report?.revision,
  ]);
  async function login(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      await api("session", {
        method: "POST",
        headers: key ? { Authorization: "Bearer " + key } : {},
      });
      setKey("");
      setAuth(true);
      setSessions(await api("conversations"));
    } catch {
      setError("No pude iniciar la sesión. Comprueba tu credencial de acceso.");
    } finally {
      setLoading(false);
    }
  }
  async function open(id: string) {
    setError("");
    active.current = id;
    try {
      const c = await api("conversations/" + id);
      if (active.current !== id) return;
      active.current = id;
      setConversation(c);
      setMatch(c.context.match_ids?.[0]?.toString() ?? "");
      setSidebar(false);
    } catch {
      setError("La conversación ha caducado. Crea un nuevo análisis.");
    }
  }
  function fresh() {
    active.current = null;
    setConversation(null);
    setHtml("");
    setText("");
    setMatch("");
    setError("");
    setSidebar(false);
    setView("report");
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim() || loading || conversation?.busy) return;
    setLoading(true);
    setError("");
    try {
      let c = conversation;
      if (!c) {
        c = await api("conversations", { method: "POST" });
        active.current = c!.id;
      }
      const context = match
        ? c!.context.match_ids?.[0] === Number(match)
          ? c!.context
          : { match_ids: [Number(match)] }
        : c!.context;
      const next = await api(`conversations/${c!.id}/messages`, {
        method: "POST",
        body: JSON.stringify({
          request_id: crypto.randomUUID(),
          text,
          context,
        }),
      });
      setConversation(next);
      setText("");
      setPane("chat");
      setSessions(await api("conversations"));
    } catch (e) {
      setError(
        e instanceof Error && e.message === "CONVERSATION_BUSY"
          ? "Ya hay una solicitud en curso en esta conversación."
          : "No pude enviar el mensaje. La página anterior sigue disponible.",
      );
    } finally {
      setLoading(false);
    }
  }
  function suggestion(value: string) {
    setText(value);
    setPane("chat");
    input.current?.focus();
  }
  const currentMatch = matches.find((m) => m.match_id === Number(match));
  return (
    <div className="workspace" data-theme={theme}>
      <aside
        id="conversation-drawer"
        ref={drawer}
        role={mobile ? "dialog" : undefined}
        aria-modal={mobile && sidebar ? true : undefined}
        aria-hidden={mobile && !sidebar}
        inert={mobile && !sidebar}
        className={`work-sidebar ${sidebar ? "is-open" : ""}`}
        aria-label="Conversaciones"
      >
        <button
          className="drawer-close icon-button"
          ref={closeButton}
          onClick={() => setSidebar(false)}
          aria-label="Cerrar conversaciones"
        >
          <Icon name="close" />
        </button>
        <a className="work-brand" href="/" aria-label="Inside the game, inicio">
          <svg
            viewBox="0 0 32 32"
            width="28"
            height="28"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <rect x="3" y="5" width="26" height="22" rx="2" />
            <path d="M16 5v22M3 12h5v8H3m26-8h-5v8h5" />
            <circle cx="16" cy="16" r="4" />
          </svg>
          <span>
            inside the game<span className="brand-period">.</span>
          </span>
        </a>
        <button
          className="new-analysis"
          onClick={fresh}
          aria-label="Nuevo análisis"
          disabled={loading}
        >
          <Icon name="plus" />
          <span>Nuevo análisis</span>
        </button>
        <p className="sidebar-label">Conversaciones</p>
        <nav className="conversation-list" aria-label="Historial">
          {sessions.length ? (
            sessions.map((s) => (
              <button
                key={s.id}
                className={conversation?.id === s.id ? "selected" : ""}
                onClick={() => open(s.id)}
                aria-label={s.title}
              >
                <Icon name="chat" />
                <span>{s.title}</span>
                {s.busy && <i className="busy-dot" />}
              </button>
            ))
          ) : (
            <p className="sidebar-empty">Tus análisis aparecerán aquí.</p>
          )}
        </nav>
        <div className="sidebar-bottom">
          <button
            className="theme-switch"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label={
              theme === "dark"
                ? "Cambiar a tema claro"
                : "Cambiar a tema oscuro"
            }
          >
            <Icon name={theme === "dark" ? "sun" : "moon"} />
            <span>{theme === "dark" ? "Tema claro" : "Tema oscuro"}</span>
          </button>
          <div className="session-info">
            <span className="session-avatar">IG</span>
            <span>
              {local ? "Demo local" : "Equipo de análisis"}
              <small>Conversaciones · 1 hora</small>
            </span>
            {auth && (
              <button
                className="icon-button"
                aria-label="Cerrar sesión"
                onClick={async () => {
                  await api("session", { method: "DELETE" });
                  setAuth(false);
                  setSessions([]);
                  fresh();
                }}
              >
                <Icon name="logout" />
              </button>
            )}
          </div>
        </div>
      </aside>
      <div className="work-main" inert={mobile && sidebar}>
        <header className="workspace-topbar">
          <button
            className="icon-button mobile-menu"
            ref={menuButton}
            aria-expanded={sidebar}
            aria-controls="conversation-drawer"
            aria-label="Mostrar conversaciones"
            onClick={() => setSidebar(!sidebar)}
          >
            <Icon name="menu" />
          </button>
          <span className="workspace-name">Espacio de análisis</span>
          <a href="/viewer" className="viewer-link">
            Abrir visor de posiciones <Icon name="arrow" />
          </a>
          <div className="mobile-tabs">
            <button
              aria-pressed={pane === "document"}
              onClick={() => setPane("document")}
            >
              Informe
            </button>
            <button
              aria-pressed={pane === "chat"}
              onClick={() => setPane("chat")}
            >
              Chat{conversation?.busy ? " ···" : ""}
            </button>
          </div>
        </header>
        {error && (
          <div className="workspace-error" role="alert">
            {error}
            <button onClick={() => setError("")} aria-label="Cerrar aviso">
              ×
            </button>
          </div>
        )}
        {!auth ? (
          <main className="workspace-login">
            <div className="login-content">
              <Icon name="chat" />
              <h1>
                El partido empieza
                <br />
                con una pregunta.
              </h1>
              <p>
                Entra para explorar partidos, generar un informe y afinarlo
                conversando.
              </p>
              <form onSubmit={login}>
                {!local && (
                  <label>
                    Credencial del equipo
                    <input
                      type="password"
                      autoComplete="off"
                      value={key}
                      onChange={(e) => setKey(e.target.value)}
                      placeholder="Tu clave de acceso"
                      required
                    />
                  </label>
                )}
                <button className="primary-button" disabled={loading}>
                  {loading
                    ? "Conectando…"
                    : local
                      ? "Entrar a la demo local"
                      : "Entrar al espacio"}
                  <Icon name="arrow" />
                </button>
              </form>
              <small>
                {local
                  ? "Los agentes se ejecutan con la configuración privada de este equipo."
                  : "Utiliza tu credencial individual de la API deportiva."}
              </small>
            </div>
          </main>
        ) : (
          <div className="workspace-panels" data-pane={pane}>
            <main className="document-panel" aria-label="Página de análisis">
              <div className="document-toolbar">
                <div>
                  <Icon name="file" />
                  <span>{conversation?.title ?? "Tu próximo análisis"}</span>
                  {conversation?.report && (
                    <small>v{conversation.report.revision}</small>
                  )}
                </div>
                <div className="document-actions">
                  {html && (
                    <>
                      <button
                        aria-pressed={view === "report"}
                        onClick={() => setView("report")}
                      >
                        Informe
                      </button>
                      <button
                        aria-pressed={view === "trace"}
                        onClick={() => setView("trace")}
                      >
                        Trazabilidad
                      </button>
                      <button
                        className="icon-button"
                        title="Descargar HTML"
                        aria-label="Descargar página HTML"
                        onClick={() =>
                          download(
                            html,
                            "inside-game-informe.html",
                            "text/html",
                          )
                        }
                      >
                        <Icon name="download" />
                      </button>
                    </>
                  )}
                </div>
              </div>
              {html ? (
                view === "report" ? (
                  <iframe
                    title="Informe deportivo generado"
                    sandbox="allow-scripts allow-downloads allow-modals"
                    srcDoc={documentHtml(html, theme === "dark")}
                  />
                ) : (
                  <div className="trace-view">
                    <h2>El recorrido de tu solicitud</h2>
                    <p>
                      Intención, delegaciones, hechos y resultados de las
                      herramientas.
                    </p>
                    <button
                      onClick={() =>
                        download(
                          JSON.stringify(conversation?.runs, null, 2),
                          "inside-game-trace.json",
                          "application/json",
                        )
                      }
                    >
                      Descargar JSON <Icon name="download" />
                    </button>
                    <pre>{JSON.stringify(conversation?.runs, null, 2)}</pre>
                  </div>
                )
              ) : (
                <div className="document-empty">
                  <svg
                    className="empty-pitch"
                    viewBox="0 0 420 240"
                    fill="none"
                    aria-hidden="true"
                  >
                    <rect x="20" y="20" width="380" height="200" rx="2" />
                    <path d="M210 20v200M20 65h66v110H20m380-110h-66v110h66M20 94h25v52H20m380-52h-25v52h25" />
                    <circle cx="210" cy="120" r="35" />
                    <path
                      className="pitch-connection"
                      d="m128 64 49 60 62-48 54 68-116-20 18 59"
                    />
                    <g className="pitch-players">
                      {[
                        [128, 64],
                        [177, 124],
                        [239, 76],
                        [293, 144],
                        [195, 183],
                      ].map(([x, y]) => (
                        <circle key={x} cx={x} cy={y} r="5" />
                      ))}
                    </g>
                  </svg>
                  <h1>
                    Otra forma de
                    <br />
                    leer el partido.
                  </h1>
                  <p>
                    De una pregunta a una página con datos,
                    <br />
                    gráficos y una lectura deportiva.
                  </p>
                  <div className="starting-points">
                    <button
                      onClick={() =>
                        suggestion(
                          "Crea un mapa de tiros y un análisis de las ocasiones del partido seleccionado.",
                        )
                      }
                    >
                      <span>
                        Explorar las ocasiones
                        <small>
                          Tiros, ubicaciones y resultados disponibles
                        </small>
                      </span>
                      <Icon name="arrow" />
                    </button>
                    <button
                      onClick={() =>
                        suggestion(
                          "Analiza la red de pases del equipo local en el primer tiempo del partido seleccionado.",
                        )
                      }
                    >
                      <span>
                        Entender la circulación
                        <small>Conexiones y estructura de los pases</small>
                      </span>
                      <Icon name="arrow" />
                    </button>
                    <button
                      onClick={() =>
                        suggestion(
                          "Quiero analizar la forma y conectividad del equipo local. ¿Qué instante necesitas?",
                        )
                      }
                    >
                      <span>
                        Leer la estructura del equipo
                        <small>Forma, proximidad y espacio ocupado</small>
                      </span>
                      <Icon name="arrow" />
                    </button>
                  </div>
                  {conversation?.busy && (
                    <p className="empty-progress">
                      <span className="busy-dot" />
                      {stages[conversation.stage]}
                    </p>
                  )}
                </div>
              )}
            </main>
            <aside className="chat-panel" aria-label="Chat con el intérprete">
              <div className="chat-heading">
                <span>Asistente del partido</span>
                <span className="agent-label">Intérprete</span>
              </div>
              <div className="chat-messages" aria-live="polite">
                {!conversation?.messages.length && (
                  <div className="chat-welcome">
                    <span className="assistant-mark">
                      <Icon name="chat" />
                    </span>
                    <h2>¿Qué quieres descubrir?</h2>
                    <p>
                      Elige un partido y cuéntame qué te interesa. Coordinaré
                      los datos, los gráficos y el análisis.
                    </p>
                    <p className="chat-tip">
                      Después puedes pedirme cambios:
                      <br />
                      «Añade el reparto del espacio»
                      <br />
                      «Compara a estos dos jugadores»
                    </p>
                  </div>
                )}
                {conversation?.messages.map((m, i) => (
                  <div key={i} className={"chat-message " + m.role}>
                    <span>{m.role === "user" ? "Tú" : "Inside the game"}</span>
                    <p>{m.content}</p>
                    {m.error && <small>{m.error}</small>}
                  </div>
                ))}
                {conversation?.busy && (
                  <div className="chat-working" role="status">
                    <span className="busy-dot" />
                    {stages[conversation.stage] ?? "Trabajando…"}
                  </div>
                )}
                <div ref={end} />
              </div>
              <form className="chat-composer" onSubmit={submit}>
                <label className="match-label" htmlFor="chat-match">
                  Partido
                </label>
                <select
                  id="chat-match"
                  value={match}
                  disabled={conversation?.busy}
                  onChange={(e) => setMatch(e.target.value)}
                >
                  <option value="">
                    {catalogLoading
                      ? "Cargando partidos…"
                      : "Seleccionar partido"}
                  </option>
                  {matches.map((m) => (
                    <option key={m.match_id} value={m.match_id}>
                      {m.home_team_name} — {m.away_team_name} · {m.match_id}
                    </option>
                  ))}
                </select>
                {currentMatch && (
                  <span className="match-source">
                    {currentMatch.is_synthetic ||
                    currentMatch.data_kind === "synthetic"
                      ? "Datos sintéticos"
                      : "Datos reales · identidades sustituidas"}
                  </span>
                )}
                {!catalogLoading && !matches.length && (
                  <button
                    type="button"
                    className="reload-catalog"
                    onClick={() => {
                      setCatalogLoading(true);
                      api("chat-catalog")
                        .then((d) => setMatches(d.matches))
                        .catch(() =>
                          setError(
                            "Los partidos siguen sin estar disponibles.",
                          ),
                        )
                        .finally(() => setCatalogLoading(false));
                    }}
                  >
                    Recargar partidos
                  </button>
                )}
                <div className="composer-input">
                  <textarea
                    ref={input}
                    aria-label="Mensaje al intérprete"
                    maxLength={4000}
                    value={text}
                    placeholder="Pregunta sobre el partido…"
                    disabled={conversation?.busy}
                    onChange={(e) => setText(e.target.value)}
                    onKeyDown={(e) => {
                      if (
                        e.key === "Enter" &&
                        !e.shiftKey &&
                        !e.nativeEvent.isComposing
                      ) {
                        e.preventDefault();
                        e.currentTarget.form?.requestSubmit();
                      }
                    }}
                  />
                  <button
                    className="send-button"
                    disabled={!text.trim() || loading || conversation?.busy}
                    aria-label="Enviar mensaje"
                  >
                    <Icon name="send" />
                  </button>
                </div>
                <small>Enter para enviar · Mayús + Enter para otra línea</small>
              </form>
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}
