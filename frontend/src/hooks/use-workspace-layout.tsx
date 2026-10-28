import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { CSSProperties, KeyboardEvent, PointerEvent } from "react";
import { clampPanel } from "../domain/workspace-feedback.ts";

type Panel = "chat" | "history";
export function useWorkspaceLayout(active = true) {
  const [layout, setLayout] = useState(() => {
    try {
      const s = JSON.parse(localStorage.getItem("inside-game-layout") ?? "{}");
      return {
        chat: clampPanel(Number(s.chat) || 350, 2000, "chat"),
        history: clampPanel(Number(s.history) || 220, 2000, "history"),
        side: s.side === "left" ? "left" : "right",
        collapsed: !!s.collapsed,
      };
    } catch {
      return { chat: 350, history: 220, side: "right", collapsed: false };
    }
  });
  const [dragging, setDragging] = useState<Panel | null>(null);
  const [moved, setMoved] = useState(false);
  const panels = useRef<HTMLDivElement>(null);
  const drag = useRef<{
    panel: Panel;
    x: number;
    width: number;
    max: number;
    sign: number;
  } | null>(null);
  const raf = useRef(0),
    pending = useRef(0);
  const moveFrom = useRef<DOMRect | null>(null),
    motion = useRef<Animation | null>(null);
  useEffect(() => {
    const t = setTimeout(
      () => localStorage.setItem("inside-game-layout", JSON.stringify(layout)),
      150,
    );
    return () => clearTimeout(t);
  }, [layout]);
  useEffect(() => () => cancelAnimationFrame(raf.current), []);
  useEffect(() => {
    const adjust = () => {
      if (!active || innerWidth <= 760) return;
      setLayout((prev) => {
        const chat = clampPanel(prev.chat, available("chat"), "chat");
        const history = clampPanel(prev.history, innerWidth, "history");
        return chat === prev.chat && history === prev.history
          ? prev
          : { ...prev, chat, history };
      });
    };
    const observer = new ResizeObserver(adjust);
    if (active && panels.current) observer.observe(panels.current);
    window.addEventListener("resize", adjust);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", adjust);
    };
  }, [active]);
  useLayoutEffect(() => {
    const el = panels.current?.querySelector<HTMLElement>(".chat-panel");
    if (!el || !moveFrom.current) return;
    const from = moveFrom.current;
    moveFrom.current = null;
    motion.current?.cancel();
    if (matchMedia("(prefers-reduced-motion:reduce)").matches) return;
    const dx = from.left - el.getBoundingClientRect().left;
    motion.current = el.animate(
      [{ transform: `translateX(${dx}px)` }, { transform: "translateX(0)" }],
      { duration: 200, easing: "cubic-bezier(0.23, 1, 0.32, 1)" },
    );
  }, [layout.side]);
  function available(panel: Panel) {
    return panel === "chat"
      ? (panels.current?.getBoundingClientRect().width ?? innerWidth - 220)
      : innerWidth;
  }
  function change(panel: Panel, width: number) {
    setLayout((prev) => ({
      ...prev,
      [panel]: clampPanel(width, available(panel), panel),
    }));
  }
  function grip(panel: Panel) {
    return {
      role: "separator" as const,
      tabIndex: 0,
      "aria-orientation": "vertical" as const,
      "aria-label":
        panel === "chat" ? "Resize assistant panel" : "Resize history panel",
      "aria-valuemin": panel === "chat" ? 250 : 170,
      "aria-valuemax": Math.max(
        panel === "chat" ? 250 : 170,
        Math.min(
          panel === "chat" ? 620 : 300,
          available(panel) - (panel === "chat" ? 290 : 700),
        ),
      ),
      "aria-valuenow": layout[panel],
      onDoubleClick: () => change(panel, panel === "chat" ? 350 : 220),
      onPointerDown: (event: PointerEvent<HTMLDivElement>) => {
        if (event.button !== 0) return;
        event.preventDefault();
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = {
          panel,
          x: event.clientX,
          width: layout[panel],
          max: available(panel),
          sign: panel === "chat" && layout.side === "right" ? -1 : 1,
        };
        setDragging(panel);
      },
      onPointerMove: (event: PointerEvent<HTMLDivElement>) => {
        const d = drag.current;
        if (!d) return;
        pending.current = d.width + (event.clientX - d.x) * d.sign;
        if (!raf.current)
          raf.current = requestAnimationFrame(() => {
            raf.current = 0;
            change(d.panel, pending.current);
          });
      },
      onPointerUp: (event: PointerEvent<HTMLDivElement>) => {
        if (drag.current) {
          if (raf.current) cancelAnimationFrame(raf.current);
          raf.current = 0;
          const d = drag.current;
          change(d.panel, d.width + (event.clientX - d.x) * d.sign);
          drag.current = null;
          setDragging(null);
        }
      },
      onLostPointerCapture: () => {
        drag.current = null;
        setDragging(null);
      },
      onPointerCancel: () => {
        drag.current = null;
        setDragging(null);
      },
      onKeyDown: (event: KeyboardEvent<HTMLDivElement>) => {
        let width = layout[panel];
        const step = event.shiftKey ? 40 : 10;
        if (event.key === "ArrowLeft") width -= step;
        else if (event.key === "ArrowRight") width += step;
        else if (event.key === "Home") width = panel === "chat" ? 250 : 170;
        else if (event.key === "End") width = panel === "chat" ? 620 : 300;
        else return;
        event.preventDefault();
        change(panel, width);
      },
    };
  }
  return {
    panels,
    layout,
    dragging,
    moved,
    grip,
    style: {
      "--history-width": layout.collapsed ? "62px" : `${layout.history}px`,
      "--chat-width": `${layout.chat}px`,
    } as CSSProperties,
    toggleHistory: () => setLayout((p) => ({ ...p, collapsed: !p.collapsed })),
    moveChat: () => {
      moveFrom.current =
        panels.current?.querySelector(".chat-panel")?.getBoundingClientRect() ??
        null;
      setMoved(true);
      setLayout((p) => ({ ...p, side: p.side === "right" ? "left" : "right" }));
    },
    reset: () =>
      setLayout({ chat: 350, history: 220, side: "right", collapsed: false }),
  };
}
