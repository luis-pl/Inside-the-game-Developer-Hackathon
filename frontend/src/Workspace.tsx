import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { FormEvent } from "react";
import "./workspace.css";
import { useTheme } from "./hooks/use-theme.ts";
import { Icon } from "./components/Icon.tsx";
import { Brand } from "./components/Brand.tsx";
import { ThemeToggle } from "./components/ThemeToggle.tsx";
import "./analyst-workspace.css";
import { AgentPipeline } from "./components/AgentPipeline.tsx";
import { RunActivity } from "./components/RunActivity.tsx";
import { useWorkspaceLayout } from "./hooks/use-workspace-layout.tsx";
import { documentHtml } from "./report-document.ts";
import {
  changeLabel,
  friendlyIssue,
  hasScopedAnalysis,
  reportLinkLabel,
} from "./domain/workspace-feedback.ts";
import type { ReportChanges } from "./domain/workspace-feedback.ts";

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
  messages: {
    role: string;
    content: string;
    error?: string;
    retry_analysis?: boolean;
  }[];
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
  changes?: ReportChanges;
  started_at?: number;
  events?: { stage: string; at: number }[];
};
type Summary = { id: string; title: string; busy: boolean };
const stages: Record<string, string> = {
  queued: "Request queued",
  catalog: "Checking match catalogue",
  interpreting: "Understanding your question",
  data: "Retrieving match evidence",
  analysis: "Analysing the match and preparing charts",
  editing: "Updating your report",
  partial: "Report ready with partial results",
  complete: "Request complete",
  clarification: "One more detail is needed",
  error: "Analysis interrupted",
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
function download(text: string, name: string, type: string) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
export function Workspace() {
  const [mobile, setMobile] = useState(
    () => matchMedia("(max-width:760px)").matches,
  );
  const { theme, toggleTheme } = useTheme();
  const [auth, setAuth] = useState(false),
    [local, setLocal] = useState(false),
    [key, setKey] = useState("");
  const sizing = useWorkspaceLayout(auth);
  const frame = useRef<HTMLIFrameElement>(null);
  const pendingRequest = useRef(false);
  const displayedRevision = useRef<{ id: string; revision: number } | null>(
    null,
  );
  const [loadedChanges, setLoadedChanges] = useState<ReportChanges | null>(
    null,
  );
  const [notice, setNotice] = useState(false),
    [documentReady, setDocumentReady] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [nearEnd, setNearEnd] = useState(true),
    [unread, setUnread] = useState(false);
  const messageScroll = useRef<HTMLDivElement>(null);
  const [sessions, setSessions] = useState<Summary[]>([]),
    [conversation, setConversation] = useState<Conversation | null>(null);
  const [matches, setMatches] = useState<Match[]>([]),
    [match, setMatch] = useState("");
  const [text, setText] = useState(""),
    [html, setHtml] = useState(""),
    [error, setError] = useState("");
  const [loading, setLoading] = useState(false),
    [catalogLoading, setCatalogLoading] = useState(false);
  const [pane, setPane] = useState("chat"),
    [view, setView] = useState("report"),
    [sidebar, setSidebar] = useState(false);
  const frameToken = useMemo(() => crypto.randomUUID(), [html, theme]);
  const [focusTarget, setFocusTarget] = useState<
    "changes" | "analysis" | "graphics" | "title" | null
  >(null);
  const renderedDocument = useMemo(
    () => documentHtml(html, theme === "dark", frameToken, loadedChanges),
    [html, theme, frameToken, loadedChanges],
  );
  useLayoutEffect(() => {
    setDocumentReady(false);
    // El iframe confirma su propio DOM. Una nueva revisión puede reutilizar
    // exactamente el mismo HTML; consultar el servidor no implica recargarlo.
    const ready = (event: MessageEvent) => {
      if (
        event.source === frame.current?.contentWindow &&
        event.data?.type === "inside-game-ready" &&
        event.data?.token === frameToken
      )
        setDocumentReady(true);
    };
    window.addEventListener("message", ready);
    return () => window.removeEventListener("message", ready);
  }, [renderedDocument, frameToken, view]);
  useEffect(() => {
    if (!focusTarget || !documentReady || view !== "report") return;
    frame.current?.contentWindow?.postMessage(
      { type: "inside-game-focus", token: frameToken, target: focusTarget },
      "*",
    );
    setFocusTarget(null);
  }, [focusTarget, documentReady, view, pane, frameToken]);
  function focusDocument(
    target: "changes" | "analysis" | "graphics" | "title",
  ) {
    setPane("document");
    setView("report");
    setFocusTarget(target);
  }
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
    api("config")
      .then((c) => setLocal(c.local_demo))
      .catch(() =>
        setError(
          "The analysis service is unavailable. Check that the workspace server is running, then refresh.",
        ),
      );
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
        setError("Could not load matches. Select Reload matches to try again."),
      )
      .finally(() => setCatalogLoading(false));
  }, [auth]);
  useEffect(() => {
    if (nearEnd) {
      end.current?.scrollIntoView({
        block: "end",
        behavior: matchMedia("(prefers-reduced-motion:reduce)").matches
          ? "instant"
          : "smooth",
      });
      setUnread(false);
    } else setUnread(true);
  }, [conversation?.messages.length, conversation?.stage, nearEnd]);
  useEffect(() => {
    if (!conversation?.busy) return;
    const start =
      conversation.started_at ??
      [...(conversation.events ?? [])]
        .reverse()
        .find((e) => e.stage === "queued")?.at ??
      Date.now() / 1000;
    const tick = () =>
      setElapsed(Math.max(0, Math.floor(Date.now() / 1000 - start)));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [conversation?.busy, conversation?.started_at, conversation?.id]);
  useEffect(() => {
    if (!conversation?.busy) return;
    const id = conversation.id;
    const timer = setInterval(
      () =>
        api("conversations/" + id)
          .then((c) => {
            if (active.current === id) setConversation(c);
            if (!c.busy)
              api("conversations")
                .then(setSessions)
                .catch(() => {});
          })
          .catch(() =>
            setError(
              "Connection lost. Reopen the conversation to recover its status.",
            ),
          ),
      2500,
    );
    return () => clearInterval(timer);
  }, [conversation?.id, conversation?.busy]);
  useEffect(() => {
    if (!conversation?.report) return;
    const id = conversation.id;
    const controller = new AbortController();
    const changes = conversation.changes ?? null;
    const revision = conversation.report.revision;
    fetch("/workspace-api/conversations/" + id + "/page", {
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then(async (r) => {
        if (!r.ok) throw Error();
        const h = await r.text();
        if (active.current === id && !controller.signal.aborted) {
          setHtml(h);
          setLoadedChanges(changes);
          setNotice(
            pendingRequest.current ||
              !!(
                displayedRevision.current?.id === id &&
                revision > displayedRevision.current.revision
              ),
          );
          displayedRevision.current = { id, revision };
          if (!conversation.busy) pendingRequest.current = false;
        }
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            "Could not load this version. Your current report is still available.",
          );
      });
    return () => controller.abort();
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
      setError("Could not sign in. Check your access credential.");
    } finally {
      setLoading(false);
    }
  }
  async function open(id: string) {
    setError("");
    if (active.current !== id) {
      setHtml("");
      setLoadedChanges(null);
      setNotice(false);
      pendingRequest.current = false;
      displayedRevision.current = null;
      setNearEnd(true);
    }
    active.current = id;
    try {
      const c = await api("conversations/" + id);
      if (active.current !== id) return;
      active.current = id;
      setConversation(c);
      setMatch(c.context.match_ids?.[0]?.toString() ?? "");
      setSidebar(false);
    } catch {
      setError("This conversation has expired. Start a new analysis.");
    }
  }
  function fresh() {
    active.current = null;
    setConversation(null);
    setHtml("");
    setLoadedChanges(null);
    setNotice(false);
    pendingRequest.current = false;
    displayedRevision.current = null;
    setText("");
    setMatch("");
    setError("");
    setSidebar(false);
    setView("report");
  }
  async function sendMessage(value: string, retryAnalysis = false) {
    if (!value.trim() || loading || conversation?.busy) return;
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
          text: value,
          context,
          retry_analysis: retryAnalysis,
        }),
      });
      setConversation(next);
      pendingRequest.current = true;
      setNearEnd(true);
      setText("");
      setPane("chat");
      void api("conversations")
        .then(setSessions)
        .catch(() => {});
    } catch (e) {
      setError(
        e instanceof Error && e.message === "CONVERSATION_BUSY"
          ? "A request is already running in this conversation."
          : "Could not send your message. Your previous report is still available.",
      );
    } finally {
      setLoading(false);
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    void sendMessage(text);
  }
  function suggestion(value: string) {
    setText(value);
    setPane("chat");
    input.current?.focus();
  }
  const currentMatch = matches.find((m) => m.match_id === Number(match));
  const scopedAnalysis = hasScopedAnalysis(conversation?.runs ?? []);
  return (
    <div
      className="workspace app-theme"
      data-theme={theme}
      style={sizing.style}
      data-history-collapsed={sizing.layout.collapsed}
      data-resizing={sizing.dragging ?? undefined}
    >
      <aside
        id="conversation-drawer"
        ref={drawer}
        role={mobile ? "dialog" : undefined}
        aria-modal={mobile && sidebar ? true : undefined}
        aria-hidden={mobile && !sidebar}
        inert={mobile && !sidebar}
        className={`work-sidebar ${sidebar ? "is-open" : ""}`}
        aria-label="Analysis history"
      >
        <button
          className="drawer-close icon-button"
          ref={closeButton}
          onClick={() => setSidebar(false)}
          aria-label="Close analysis history"
        >
          <Icon name="close" />
        </button>
        <Brand />
        <button
          className="new-analysis"
          onClick={fresh}
          aria-label="New analysis"
          disabled={loading}
        >
          <Icon name="plus" />
          <span>New analysis</span>
        </button>
        <p className="sidebar-label">Analysis history</p>
        <nav className="conversation-list" aria-label="History">
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
            <p className="sidebar-empty">
              Your match analyses will appear here.
            </p>
          )}
        </nav>
        <div className="sidebar-bottom">
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
          <div className="session-info">
            <span className="session-avatar">IG</span>
            <span>
              {local ? "Local demo" : "Analysis team"}
              <small>Session history · 1 hour</small>
            </span>
            {auth && (
              <button
                className="icon-button"
                aria-label="Sign out"
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
      {!sizing.layout.collapsed && (
        <div
          className="panel-grip history-grip"
          {...sizing.grip("history")}
          title="Drag to resize · Arrow keys to adjust · Double-click to reset"
        >
          <span />
        </div>
      )}
      <div className="work-main" inert={mobile && sidebar}>
        <header className="workspace-topbar">
          <button
            className="icon-button desktop-layout-control"
            onClick={sizing.toggleHistory}
            aria-label={
              sizing.layout.collapsed ? "Expand history" : "Collapse history"
            }
            title={
              sizing.layout.collapsed ? "Expand history" : "Collapse history"
            }
          >
            <Icon name="dock" />
          </button>
          <button
            className="icon-button mobile-menu"
            ref={menuButton}
            aria-expanded={sidebar}
            aria-controls="conversation-drawer"
            aria-label="Show analysis history"
            onClick={() => setSidebar(!sidebar)}
          >
            <Icon name="menu" />
          </button>
          <span className="workspace-name">
            <small>FOOTBALL INTELLIGENCE</small>Agent workspace
          </span>
          <div className="layout-controls">
            <button
              className="icon-button"
              onClick={sizing.moveChat}
              aria-label={
                sizing.layout.side === "right"
                  ? "Move assistant to the left"
                  : "Move assistant to the right"
              }
              title="Switch assistant panel side"
            >
              <Icon name="dock" />
            </button>
            <button
              className="icon-button"
              onClick={sizing.reset}
              aria-label="Reset panel layout"
              title="Reset panel layout"
            >
              <Icon name="reset" />
            </button>
          </div>
          <a href="/viewer" className="viewer-link">
            Match viewer <Icon name="arrow" />
          </a>
          <div className="mobile-tabs">
            <button
              aria-pressed={pane === "document"}
              onClick={() => setPane("document")}
            >
              Report
            </button>
            <button
              aria-pressed={pane === "chat"}
              onClick={() => setPane("chat")}
            >
              Chat{conversation?.busy ? " ···" : ""}
            </button>
          </div>
        </header>
        {auth && (
          <AgentPipeline
            stage={conversation?.stage}
            busy={conversation?.busy ?? false}
            match={
              currentMatch
                ? `${currentMatch.home_team_name} vs ${currentMatch.away_team_name}`
                : undefined
            }
          />
        )}
        {error && (
          <div className="workspace-error" role="alert">
            {error}
            <button onClick={() => setError("")} aria-label="Dismiss notice">
              ×
            </button>
          </div>
        )}
        {!auth ? (
          <main className="workspace-login">
            <div className="login-content">
              <Icon name="chat" />
              <span className="workspace-eyebrow">
                YOUR FOOTBALL ANALYSIS TEAM
              </span>
              <h1>
                Better questions.
                <br />A clearer game.
              </h1>
              <p>
                Ask a football question. Your agents bring together the
                evidence, the analysis and the visual report.
              </p>
              <div className="login-capabilities">
                <span>
                  01 <b>Ask</b>
                </span>
                <span>
                  02 <b>Analyse</b>
                </span>
                <span>
                  03 <b>Explore</b>
                </span>
              </div>
              <form onSubmit={login}>
                {!local && (
                  <label>
                    Team access credential
                    <input
                      type="password"
                      autoComplete="off"
                      value={key}
                      onChange={(e) => setKey(e.target.value)}
                      placeholder="Your access key"
                      required
                    />
                  </label>
                )}
                <button className="primary-button" disabled={loading}>
                  {loading
                    ? "Connecting…"
                    : local
                      ? "Open local workspace"
                      : "Enter workspace"}
                  <Icon name="arrow" />
                </button>
              </form>
              <small>
                {local
                  ? "Uses this computer's configured analysis services."
                  : "Sign in with your individual football API credential."}
              </small>
            </div>
          </main>
        ) : (
          <div
            className="workspace-panels"
            data-pane={pane}
            ref={sizing.panels}
            data-chat-side={sizing.layout.side}
            data-layout-moved={sizing.moved}
          >
            <main className="document-panel" aria-label="Analysis report">
              <div className="document-toolbar">
                <div>
                  <Icon name="file" />
                  <span>{conversation?.title ?? "Match analysis"}</span>
                  {conversation?.report && (
                    <small>v{conversation.report.revision}</small>
                  )}
                </div>
                <div className="document-actions">
                  {Boolean(html || conversation?.runs.length) && (
                    <>
                      <button
                        aria-pressed={view === "report"}
                        onClick={() => setView("report")}
                      >
                        Report
                      </button>
                      <button
                        aria-pressed={view === "trace"}
                        onClick={() => setView("trace")}
                      >
                        Activity
                      </button>
                      <button
                        className="icon-button"
                        disabled={!html}
                        title="Download HTML"
                        aria-label="Download report as HTML"
                        onClick={() =>
                          download(html, "inside-game-report.html", "text/html")
                        }
                      >
                        <Icon name="download" />
                      </button>
                    </>
                  )}
                </div>
              </div>
              {conversation?.busy && (
                <div className="document-loading" role="status">
                  <span className="activity-spinner" />
                  <span>
                    {stages[conversation.stage] ?? "Preparing your report"}
                    <small>
                      {html
                        ? "You can keep exploring this version."
                        : "Your report will appear here when ready."}
                    </small>
                  </span>
                  <time>{elapsed}s</time>
                </div>
              )}
              {html && notice && loadedChanges && !conversation?.busy && (
                <div className="document-update" role="status">
                  <span className="update-arrow">
                    <Icon name="down" />
                  </span>
                  <div>
                    <strong>{changeLabel(loadedChanges)}</strong>
                    <small>
                      Version {loadedChanges.revision} · Changes ready to review
                    </small>
                  </div>
                  <button
                    disabled={view === "report" && !documentReady}
                    onClick={() =>
                      focusDocument(
                        loadedChanges.title_changed &&
                          !loadedChanges.added.length &&
                          !loadedChanges.updated.length
                          ? "title"
                          : "changes",
                      )
                    }
                  >
                    Review changes <Icon name="down" />
                  </button>
                  <button
                    className="icon-button"
                    aria-label="Dismiss update notice"
                    onClick={() => setNotice(false)}
                  >
                    <Icon name="close" />
                  </button>
                </div>
              )}
              {html && (
                <nav
                  className="report-navigation"
                  aria-label="Explore the report"
                >
                  <button
                    onClick={() => focusDocument("graphics")}
                    disabled={view === "report" && !documentReady}
                  >
                    Explore charts <Icon name="down" />
                  </button>
                  <button
                    onClick={() => focusDocument("analysis")}
                    disabled={view === "report" && !documentReady}
                  >
                    Read findings
                  </button>
                </nav>
              )}
              {view === "trace" ? (
                <div className="trace-view">
                  <RunActivity
                    key={conversation?.id}
                    runs={conversation?.runs ?? []}
                    busy={conversation?.busy ?? false}
                  />
                  <button
                    className="trace-download"
                    disabled={!conversation?.runs.length}
                    onClick={() =>
                      download(
                        JSON.stringify(conversation?.runs, null, 2),
                        "inside-game-trace.json",
                        "application/json",
                      )
                    }
                  >
                    Download trace <Icon name="download" />
                  </button>
                </div>
              ) : html ? (
                <iframe
                  ref={frame}
                  title="Generated match analysis report"
                  sandbox="allow-scripts allow-downloads allow-modals"
                  srcDoc={renderedDocument}
                />
              ) : (
                <div className="document-empty">
                  <span className="workspace-eyebrow">
                    FROM YOUR QUESTION TO THE FINDINGS
                  </span>
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
                    See the patterns.
                    <br />
                    Understand the game.
                  </h1>
                  <p>
                    One conversation. A team of analysis agents.
                    <br />
                    Ask, review the evidence, then refine your report.
                  </p>
                  <div className="starting-points">
                    <button
                      onClick={() =>
                        suggestion(
                          "Create a shot map and analyse chance creation for the selected match. Write the report and chart labels in English.",
                        )
                      }
                    >
                      <span>
                        Chance creation
                        <small>Shot locations, outcomes and available xG</small>
                      </span>
                      <Icon name="arrow" />
                    </button>
                    <button
                      onClick={() =>
                        suggestion(
                          "Analyse the home team's passing network in the first half of the selected match. Write the report and chart labels in English.",
                        )
                      }
                    >
                      <span>
                        Passing & progression
                        <small>Player connections and passing structure</small>
                      </span>
                      <Icon name="arrow" />
                    </button>
                    <button
                      onClick={() =>
                        suggestion(
                          "Analyse the home team's shape and connectivity. Which match instant do you need? Reply and write the report in English.",
                        )
                      }
                    >
                      <span>
                        Team shape & space
                        <small>
                          Positioning, proximity and available space
                        </small>
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
            <div
              className="panel-grip chat-grip"
              {...sizing.grip("chat")}
              title="Drag to resize · Arrow keys to adjust · Double-click to reset"
            >
              <span />
            </div>
            <aside className="chat-panel" aria-label="Match analysis assistant">
              <div className="chat-heading">
                <span>Talk to your analyst</span>
                <span className="agent-label">Agent team</span>
              </div>
              <div
                className="chat-messages"
                aria-live="polite"
                ref={messageScroll}
                onScroll={(e) => {
                  const el = e.currentTarget;
                  setNearEnd(
                    el.scrollHeight - el.scrollTop - el.clientHeight < 70,
                  );
                }}
              >
                {!conversation?.messages.length && (
                  <div className="chat-welcome">
                    <span className="assistant-mark">
                      <Icon name="chat" />
                    </span>
                    <h2>What do you want to understand?</h2>
                    <p>
                      Select a match and set the brief. Your interpreter
                      coordinates the data, analyst and visualisation agents.
                    </p>
                    <p className="chat-tip">
                      Refine your report as you go:
                      <br />
                      “Add a spatial breakdown”
                      <br />
                      “Compare these two players”
                    </p>
                  </div>
                )}
                {conversation?.messages.map((m, i) => (
                  <div key={i} className={"chat-message " + m.role}>
                    <span>{m.role === "user" ? "You" : "Inside the game"}</span>
                    <p>{m.error ? friendlyIssue(m.error) : m.content}</p>
                    {m.error && (
                      <details className="message-debug">
                        <summary>Technical details</summary>
                        <code>{m.error}</code>
                      </details>
                    )}
                    {m.role === "assistant" &&
                      i === conversation.messages.length - 1 &&
                      !conversation.busy &&
                      (m.error ||
                        (conversation.stage === "partial" &&
                          !scopedAnalysis)) && (
                        <button
                          className="retry-action"
                          onClick={() => {
                            const last = [...conversation.messages]
                              .reverse()
                              .find((x) => x.role === "user");
                            if (last)
                              void sendMessage(
                                last.content,
                                !!m.retry_analysis,
                              );
                          }}
                        >
                          <Icon name="reset" />
                          {m.retry_analysis
                            ? "Complete analysis"
                            : "Retry request"}
                        </button>
                      )}
                    {m.role === "assistant" &&
                      i === conversation.messages.length - 1 &&
                      !conversation.busy &&
                      !m.error &&
                      conversation.report && (
                        <button
                          className="message-open-report"
                          disabled={view === "report" && !documentReady}
                          onClick={() =>
                            focusDocument(
                              loadedChanges?.title_changed &&
                                !loadedChanges.added.length &&
                                !loadedChanges.updated.length
                                ? "title"
                                : "changes",
                            )
                          }
                        >
                          {reportLinkLabel(conversation.runs)}{" "}
                          <Icon name="down" />
                        </button>
                      )}
                  </div>
                ))}
                {conversation?.busy && (
                  <div className="chat-working" role="status">
                    <div className="work-status-line">
                      <span className="activity-spinner" />
                      <strong>
                        {stages[conversation.stage] ?? "Trabajando…"}
                      </strong>
                      <time>{elapsed}s</time>
                    </div>
                    <ol className="work-steps" aria-label="Analysis progress">
                      {["Question", "Evidence", "Report"].map(
                        (label, index) => {
                          const activeIndex = [
                            "queued",
                            "catalog",
                            "interpreting",
                          ].includes(conversation.stage)
                            ? 0
                            : conversation.stage === "data"
                              ? 1
                              : 2;
                          return (
                            <li
                              key={label}
                              data-state={
                                index === activeIndex
                                  ? "active"
                                  : index < activeIndex
                                    ? "past"
                                    : "next"
                              }
                            >
                              <span />
                              {label}
                            </li>
                          );
                        },
                      )}
                    </ol>
                    <small>
                      {elapsed > 25
                        ? "Still working. Your current report remains available."
                        : "Preparing the evidence for your request."}
                    </small>
                  </div>
                )}
                <div ref={end} />
              </div>
              {unread && !nearEnd && (
                <button
                  className="new-messages"
                  onClick={() => {
                    setNearEnd(true);
                    setUnread(false);
                  }}
                >
                  New messages <Icon name="down" />
                </button>
              )}
              <form className="chat-composer" onSubmit={submit}>
                <label className="match-label" htmlFor="chat-match">
                  Match
                </label>
                <select
                  id="chat-match"
                  value={match}
                  disabled={conversation?.busy}
                  onChange={(e) => setMatch(e.target.value)}
                >
                  <option value="">
                    {catalogLoading ? "Loading matches…" : "Select a match"}
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
                      ? "Synthetic data"
                      : currentMatch.data_kind?.startsWith("real_")
                        ? "Recorded data · identities replaced"
                        : "Data provenance not specified"}
                  </span>
                )}
                {!catalogLoading && !matches.length && (
                  <button
                    type="button"
                    className="reload-catalog"
                    onClick={() => {
                      setCatalogLoading(true);
                      api("chat-catalog")
                        .then((d) => {
                          setMatches(d.matches);
                          setError((current) =>
                            [
                              "Could not load matches. Select Reload matches to try again.",
                              "Matches are still unavailable.",
                            ].includes(current)
                              ? ""
                              : current,
                          );
                        })
                        .catch(() => setError("Matches are still unavailable."))
                        .finally(() => setCatalogLoading(false));
                    }}
                  >
                    Reload matches
                  </button>
                )}
                <div className="composer-input">
                  <textarea
                    ref={input}
                    aria-label="Ask the match analyst"
                    maxLength={4000}
                    value={text}
                    placeholder="Ask about chances, passing or team shape…"
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
                    aria-label="Send message"
                  >
                    <Icon name="send" />
                  </button>
                </div>
                <small>Enter to send · Shift + Enter for a new line</small>
              </form>
            </aside>
          </div>
        )}
      </div>
    </div>
  );
}
