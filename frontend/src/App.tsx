import type { EpisodeRepository } from "./domain/types.ts";
import { useLab } from "./hooks/use-lab.ts";
import { Controls } from "./components/Controls.tsx";
import { FieldPanel } from "./components/FieldPanel.tsx";
import { Timeline } from "./components/Timeline.tsx";
import { HodgePanel } from "./components/HodgePanel.tsx";
import { NetworkDetails } from "./components/NetworkDetails.tsx";
import { AnalysisDisclosure } from "./components/AnalysisDisclosure.tsx";
import { MatchMetrics } from "./components/MatchMetrics.tsx";
import "./analyst-viewer.css";
import { useTheme } from "./hooks/use-theme.ts";
import { Brand } from "./components/Brand.tsx";
import { ThemeToggle } from "./components/ThemeToggle.tsx";

export function App({ repository }: { repository: EpisodeRepository }) {
  const lab = useLab(repository);
  const { theme, toggleTheme } = useTheme();
  return (
    <div className="analyst-viewer app-theme" data-theme={theme}>
      <a className="skip-link" href="#match-content">
        Skip to match analysis
      </a>
      <header className="viewer-header">
        <Brand />
        <nav aria-label="Analysis workspace">
          <a href="/">Reports</a>
          <a href="/viewer" aria-current="page">
            Match viewer
          </a>
        </nav>
        <ThemeToggle
          theme={theme}
          onToggle={toggleTheme}
          className="viewer-theme-toggle"
        />
      </header>
      <main className="broadcast-main" id="match-content">
        <div className="analyst-heading">
          <div>
            <p className="eyebrow">
              <span /> THE ANALYST'S WORKSPACE
            </p>
            <h1>Read the game.</h1>
            <p>
              Explore team shape, passing connections and the spaces in between.
            </p>
          </div>
          <a className="settings-link" href="#match-settings">
            Configure analysis <span aria-hidden="true">↗</span>
          </a>
        </div>
        <div className="viewer-layout">
          <aside
            className="viewer-settings"
            id="match-settings"
            aria-label="Match configuration"
          >
            <Controls lab={lab} />
          </aside>
          <div className="viewer-content">
            <MatchMetrics lab={lab} />
            <FieldPanel lab={lab} />
            <div className="pitch-reading-key" aria-label="Pitch legend">
              <span>
                <i className="mint-key" />
                {lab.episode?.teams[1].name ?? "Team 2"}
              </span>
              <span>
                <i className="amber-key" />
                {lab.episode?.teams[0].name ?? "Team 1"}
              </span>
              <span>
                <i className="space-key" />
                Open space
              </span>
              <span>
                <i className="line-key" />
                Connected to ball
              </span>
              <span className="key-note">Geometry at the selected instant</span>
            </div>
            <Timeline lab={lab} />
            <AnalysisDisclosure title="Passing structure · Hodge decomposition">
              <HodgePanel lab={lab} />
            </AnalysisDisclosure>
            <AnalysisDisclosure title="How to read the analysis · methodology & limitations">
              <NetworkDetails lab={lab} />
            </AnalysisDisclosure>
            {lab.episode?.warnings.map((warning, i) => (
              <p className="episode-notes" key={i}>
                {warning}
              </p>
            ))}
          </div>
        </div>
        <footer>
          <span>INSIDE THE GAME / MATCH INTELLIGENCE</span>
          <span>
            Original samples · transparent methods · visible provenance
          </span>
        </footer>
      </main>
    </div>
  );
}
