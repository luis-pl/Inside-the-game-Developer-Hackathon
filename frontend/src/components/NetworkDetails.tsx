import type { Lab } from "../hooks/use-lab.ts";
import { Persistence } from "./Persistence.tsx";
import { episodeTiming } from "../domain/playback.ts";

export function NetworkDetails({ lab }: { lab: Lab }) {
  const network = lab.tactics?.network;
  return (
    <section className="network-details">
      <h2>Cómo leer los nodos atacantes</h2>
      <p>
        Los aros y líneas verdes identifican atacantes conectados al balón,
        directamente o mediante compañeros. Los trazos grises discontinuos
        muestran conexiones entre atacantes que no llegan al balón en esta red.
        El contador de arriba incluye todos los atacantes enlazados; «directos»
        cuenta únicamente los vecinos del balón. La línea amarilla destaca la
        cadena hacia el espacio elegido.
      </p>
      <p>
        En modo automático, el equipo atacante es una estimación por el jugador
        más cercano al balón en cada muestra original. Se conserva el equipo
        anterior durante detenciones, ausencia de balón o empate de distancias
        entre equipos. No equivale a posesión confirmada. Los colores de los
        equipos no cambian al cambiar el rol. Puedes fijar la defensa
        manualmente en la configuración.
      </p>
      <h2>Cómo se calculan las conexiones</h2>
      <p>
        Los nodos son el balón y los jugadores del equipo atacante. Se conectan
        dos nodos si el disco cuyo diámetro es su segmento no contiene ningún
        otro jugador ni el balón: es el grafo de Gabriel de todas las
        posiciones, restringido a nodos atacantes. Un defensa dentro de ese
        disco impide esa conexión. No se selecciona una distancia máxima.
      </p>
      <p>
        Para cada arista se calcula exactamente la distancia mínima de todos los
        defensas al segmento, limitada por las bandas del campo. El doble de ese
        valor es la anchura del corredor libre de posiciones defensivas. Un
        defensa sobre el segmento produce anchura cero y elimina la arista.
      </p>
      <h3>Topología del espacio disponible</h3>
      <p>
        La filtración H₀ añade aristas de mayor a menor holgura. Kruskal obtiene
        un bosque de expansión máxima; conserva la mayor anchura mínima posible
        de cualquier cadena entre el balón y cada compañero en este grafo. No se
        elige un umbral: se recorren todos los valores críticos. Las cadenas
        indican conexiones geométricas posibles, no pases ejecutados.
      </p>
      {network && (
        <>
          <p>
            <b>{network.nodes.length}</b> nodos · <b>{network.edges.length}</b>{" "}
            conexiones · <b>{network.components}</b> componentes finales.
          </p>
          <table>
            <caption>Fusiones H₀ · anchura de corredor en metros</caption>
            <thead>
              <tr>
                <th>Anchura crítica</th>
                <th>Componentes restantes</th>
              </tr>
            </thead>
            <tbody>
              {network.merges.map((m, i) => (
                <tr key={i}>
                  <td>{(2 * m.clearance).toFixed(2)} m</td>
                  <td>{m.components}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      <h3>Espacios de ruptura</h3>
      <p>
        Se buscan centros de círculos vacíos de tres defensas, vértices de
        Voronoi, dentro de la envolvente de los jugadores de campo. El portero
        también limita el espacio. Se recortan por los límites del campo. Se
        conservan hasta tres candidatos separados con radio ≥ 1 m; este filtro
        sólo reduce lo que se dibuja, no determina conexiones.
      </p>
      <p>
        Cada espacio es un destino terminal: nunca se utiliza como un jugador
        intermediario. Se busca la cadena desde el balón que maximiza su
        corredor más estrecho. La pantalla prioriza espacios conectados por esta
        red, después su holgura, avance y tamaño. El tamaño es el diámetro del
        círculo, no la anchura de la cadena.
      </p>
      <h3>Alcance del modelo</h3>
      <p>
        Defensas modelados como posiciones puntuales. No se supone un radio de
        control, velocidad ni tiempo de reacción. «Libre» significa vacío en
        esta instantánea, no seguro frente a una intercepción. El grafo de
        Gabriel es conservador: que no exista conexión en él no demuestra que no
        exista un pase o un camino en el campo.{" "}
        {lab.episode?.dataKind?.startsWith("real_")
          ? `Datos reales con identidades enmascaradas de ${lab.episode.provider ?? "la fuente indicada"},`
          : "Datos sintéticos de demostración,"}{" "}
        con observaciones seleccionadas cada{" "}
        {episodeTiming(lab.episode).sampleStepMs / 1000} segundos. La animación
        interpola linealmente posiciones entre muestras contiguas para dibujar.
        Los cálculos topológicos utilizan exclusivamente muestras originales. No
        se interpolan huecos ni identidades ausentes. El reloj reproduce una
        ventana, no una transmisión en directo.
      </p>
      <h3>Firma del bloque · persistencia de Rips</h3>
      <p>
        Diagnóstico independiente sobre todas las escalas hasta 40 m, sobre F₂.
        Sus ciclos H₁ no son los círculos dibujados ni deciden las conexiones
        del partido.
      </p>
      {lab.analysis && <Persistence bars={lab.analysis.bars} />}
      <details className="node-comparison">
        <summary>Comparar retirando un defensor del modelo</summary>
        <p>
          Comparación geométrica, no una sustitución ni una predicción del
          movimiento del resto.
        </p>
        <div className="node-buttons">
          {lab.frame?.players
            .filter((p) => p.teamId === lab.teamId && !p.goalkeeper)
            .map((p) => (
              <button
                key={p.id}
                aria-pressed={lab.removed === p.id}
                onClick={() =>
                  lab.setRemoved(lab.removed === p.id ? null : p.id)
                }
              >
                #{p.number} · {p.name}
              </button>
            ))}
        </div>
        {lab.removed !== null && (
          <button onClick={() => lab.setRemoved(null)}>
            Restaurar bloque completo
          </button>
        )}
      </details>
    </section>
  );
}
