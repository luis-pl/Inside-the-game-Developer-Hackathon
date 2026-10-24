import type { EpisodeRepository } from "./domain/types.ts";
import { useLab } from "./hooks/use-lab.ts";
import { Controls } from "./components/Controls.tsx";
import { FieldPanel } from "./components/FieldPanel.tsx";
import { Timeline } from "./components/Timeline.tsx";
import { HodgePanel } from "./components/HodgePanel.tsx";
import { NetworkDetails } from "./components/NetworkDetails.tsx";
import { AnalysisDisclosure } from "./components/AnalysisDisclosure.tsx";

export function App({ repository }: { repository: EpisodeRepository }) {
  const lab = useLab(repository);
  return (
    <>
      <header className="app-header broadcast-header">
        <a className="brand" href="/" aria-label="Inside the game, inicio">
          <span className="brand-icon">◈</span>
          <span>
            inside<span className="brand-light">the</span>game
            <span className="brand-dot">.</span>
          </span>
        </a>
        <span className="broadcast-title">LECTURA DEL PARTIDO</span>
        <a className="text-button" href="#match-settings">
          Elegir partido ↓
        </a>
      </header>
      <main className="broadcast-main">
        <FieldPanel lab={lab} />
        <div className="below-match" id="match-settings">
          <details className="panel match-settings" open={!lab.episode}>
            <summary>Partido y equipo analizado</summary>
            <Controls lab={lab} />
          </details>
          <AnalysisDisclosure title="Explorar la ventana y sus aperturas">
            <Timeline lab={lab} />
          </AnalysisDisclosure>
          <AnalysisDisclosure title="Cómo leer la cancha y cómo funciona la matemática">
            <div className="visual-key">
              <p>
                <b className="key-defender">● Menta:</b>{" "}
                {lab.episode?.teams[1].name ?? "equipo 2"}.{" "}
                <b className="key-attacker">● Ámbar:</b>{" "}
                {lab.episode?.teams[0].name ?? "equipo 1"}. <b>● Blanco:</b>{" "}
                balón.
              </p>
              <p>
                <b>Zona amarilla:</b> espacio vacío entre defensas; su diámetro
                se lee arriba. <b>Líneas y aros verdes:</b> atacantes enlazados
                al balón. <b>Gris discontinuo:</b> nodos o conexiones separados
                del balón. <b>Línea amarilla:</b> cadena hacia el espacio
                destacado; su anchura mínima aparece arriba como «corredor
                libre». No son pases garantizados.
              </p>
            </div>
            <NetworkDetails lab={lab} />
          </AnalysisDisclosure>
          <AnalysisDisclosure title="Descomposición de Hodge · pases acumulados">
            <HodgePanel lab={lab} />
          </AnalysisDisclosure>
          {lab.episode?.warnings.map((warning, i) => (
            <p className="episode-notes" key={i}>
              {warning}
            </p>
          ))}
        </div>
        <footer>
          <span>INSIDE THE GAME / DEVELOPER HACKATHON</span>
          <span>
            Geometría de posiciones · procedencia visible en la cancha
          </span>
        </footer>
      </main>
    </>
  );
}
