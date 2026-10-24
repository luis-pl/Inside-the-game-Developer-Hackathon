import type { Episode, Player } from "../domain/types.ts";

/** Explicit pedagogical geometry, never represented as records from Azure. */
export function localScenario(): Episode {
  const defenders = [
    [100, 34],
    [79, 9],
    [79, 25],
    [79, 43],
    [79, 59],
    [63, 16],
    [62, 34],
    [63, 52],
    [46, 15],
    [45, 34],
    [46, 53],
  ];
  const attackers = [
    [5, 34],
    [24, 10],
    [26, 26],
    [26, 43],
    [24, 58],
    [42, 18],
    [43, 34],
    [42, 50],
    [68, 12],
    [72, 34],
    [68, 56],
  ];
  return {
    window: { startMs: 600000, endMs: 900000, sampleStepMs: 1000 },
    source: "local",
    matchLabel: "Laboratorio · apertura del bloque",
    period: 1,
    homeAttacksRight: true,
    teams: [
      { id: 1, name: "Equipo Ámbar" },
      { id: 2, name: "Equipo Menta" },
    ],
    warnings: [
      "Escenario geométrico generado localmente. No corresponde a un partido de la base Azure.",
      "Pases ilustrativos: un triángulo y un cuadrado sin diagonales para explorar Hodge.",
    ],
    passes: [1, 2].flatMap((team) =>
      [
        [2, 3],
        [3, 4],
        [4, 2],
        [6, 7],
        [7, 8],
        [8, 9],
        [9, 6],
        [4, 6],
      ].flatMap(([a, b], i) =>
        Array.from({ length: 2 }, (_, j) => ({
          id: `local-${team}-${i}-${j}`,
          source: team * 100 + a,
          target: team * 100 + b,
          teamId: team,
          timeMs: 600000 + (i * 5 + j) * 5000,
        })),
      ),
    ),
    events: [
      { timeMs: 675000, label: "Inicio del desplazamiento ilustrativo" },
      { timeMs: 750000, label: "Separación máxima del escenario" },
    ],
    frames: Array.from({ length: 300 }, (_, second) => {
      const phase = second / 5;
      const opening = Math.sin((second / 299) * Math.PI);
      const players: Player[] = [];
      for (const [team, coords] of [
        [1, attackers],
        [2, defenders],
      ] as const)
        coords.forEach(([x, y], i) => {
          players.push({
            id: team * 100 + i + 1,
            teamId: team,
            number: i + 1,
            name: `${team === 1 ? "Ámbar" : "Menta"} ${i + 1}`,
            goalkeeper: i === 0,
            x:
              x +
              (team === 2 && i === 2
                ? opening * 12
                : team === 2 && i === 3
                  ? opening * 6
                  : Math.sin(phase / 12 + i) * 1.2),
            y:
              y +
              (team === 2 && i === 2
                ? -opening * 6
                : team === 2 && i === 3
                  ? opening * 6
                  : Math.cos(phase / 14 + i) * 0.8),
          });
        });
      return {
        timeMs: 600000 + second * 1000,
        ballInPlay: true,
        ball: { x: 55 + phase * 0.25, y: 34 + Math.sin(phase / 10) * 3 },
        players,
      };
    }),
  };
}
