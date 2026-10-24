import { useState } from "react";
import type { ReactNode } from "react";

/** Keep large charts out of the playback render path until requested. */
export function AnalysisDisclosure({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <details
      className="panel match-explainer"
      onToggle={(event) => setExpanded(event.currentTarget.open)}
    >
      <summary>{title}</summary>
      {expanded && children}
    </details>
  );
}
