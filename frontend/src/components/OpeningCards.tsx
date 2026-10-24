import type { Opening } from "../domain/openings.ts";
export function OpeningCards({
  openings,
  selected,
  onSelect,
}: {
  openings: Opening[];
  selected: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="opening-cards">
      {openings.length ? (
        openings.map((opening) => (
          <button
            key={opening.id}
            className={selected === opening.id ? "active" : ""}
            aria-pressed={selected === opening.id}
            onClick={() => onSelect(opening.id)}
          >
            <span className="opening-number">{opening.id}</span>
            <span>
              <strong>{opening.diameter.toFixed(1)} m de espacio</strong>
              <small>
                {opening.ballConnected === null
                  ? "Conexión al balón desconocida"
                  : opening.ballConnected
                    ? "Conectada con el balón"
                    : "Sin conexión con el balón"}
              </small>
            </span>
            <span className="opening-status">
              {opening.ballConnected ? "↗" : "○"}
            </span>
          </button>
        ))
      ) : (
        <p className="small muted">
          No se detectan círculos libres de al menos 1 m de radio dentro del
          bloque con este ajuste. Puede haber espacio por fuera del bloque.
        </p>
      )}
      <p className="opening-help">
        Cada círculo cabe sin tocar las zonas de cobertura. Su tamaño es el
        diámetro. Se destacan hasta tres aperturas; las etiquetas se recalculan
        en cada muestra.
      </p>
    </div>
  );
}
