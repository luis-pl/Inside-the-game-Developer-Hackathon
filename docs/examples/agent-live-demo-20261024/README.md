# Demostración real del agente de datos

Modelo: `beam-free`. Estado: **complete**.

## Entrada entregada al agente

En el partido Synthetic FC 1 contra Synthetic FC 2 del 2026-10-01, obtén el contexto del partido y todos los tiros a puerta del equipo local, con su resumen, momento y coordenadas. Resuelve el partido por sus nombres y fecha; entrega la evidencia original sin realizar análisis deportivo.

La entrada no incluye IDs ni consultas preseleccionadas. Los nombres y la fecha se tomaron del catálogo antes de esta ejecución.

## Prompt utilizado

SHA-256: `7b6b9c567c5fb71b8b9dba8be242b47c6dd6bc4fd319feba5d67a08ddb5f4b33`.

[Copia exacta del prompt](prompt-used.md) · [Entrada JSON](input.json) · [Catálogo de herramientas](tools-catalog.json)

## Secuencia observada

### 5. find_entities · 6.937 s

```json
{
  "limit": 100,
  "cursor": null,
  "kind": "team",
  "name": "Synthetic FC 1",
  "match_id": null
}
```

Respuesta MCP: correcta. [Datos completos en la traza](trace.jsonl).

### 9. find_entities · 8.437 s

```json
{
  "limit": 100,
  "cursor": null,
  "kind": "team",
  "name": "Synthetic FC 2",
  "match_id": null
}
```

Respuesta MCP: correcta. [Datos completos en la traza](trace.jsonl).

### 13. list_matches · 9.812 s

```json
{
  "limit": 100,
  "cursor": null,
  "team_id": 1,
  "opponent_id": 2,
  "from_date": "2026-10-01",
  "to_date": "2026-10-01",
  "side": "all"
}
```

Respuesta MCP: correcta. [Datos completos en la traza](trace.jsonl).

### 17. get_match_context · 12.562 s

```json
{
  "match_id": 900001
}
```

Respuesta MCP: correcta. [Datos completos en la traza](trace.jsonl).

### 21. get_shots · 13.906 s

```json
{
  "limit": 100,
  "cursor": null,
  "match_id": 900001,
  "team_id": 1,
  "player_id": null,
  "scope": {
    "kind": "match"
  },
  "zone_id": "all",
  "score_state": "all",
  "pressure": "all",
  "view": "summary",
  "bin_s": 300,
  "outcome": "on_target",
  "body_part": "all"
}
```

Respuesta MCP: correcta. [Datos completos en la traza](trace.jsonl).

### 25. get_shots · 15.281 s

```json
{
  "limit": 100,
  "cursor": null,
  "match_id": 900001,
  "team_id": 1,
  "player_id": null,
  "scope": {
    "kind": "match"
  },
  "zone_id": "all",
  "score_state": "all",
  "pressure": "all",
  "view": "events",
  "bin_s": 300,
  "outcome": "on_target",
  "body_part": "all"
}
```

Respuesta MCP: correcta. [Datos completos en la traza](trace.jsonl).

### 29. get_shots · 16.594 s

```json
{
  "limit": 100,
  "cursor": null,
  "match_id": 900001,
  "team_id": 1,
  "player_id": null,
  "scope": {
    "kind": "match"
  },
  "zone_id": "all",
  "score_state": "all",
  "pressure": "all",
  "view": "map",
  "bin_s": 300,
  "outcome": "on_target",
  "body_part": "all"
}
```

Respuesta MCP: correcta. [Datos completos en la traza](trace.jsonl).

### Finalización propuesta por el modelo

```json
{
  "evidence_ids": [
    "e1",
    "e2",
    "e3",
    "e4",
    "e5",
    "e6",
    "e7"
  ],
  "notes": [
    "Match resolved: match_id 900001, Synthetic FC 1 (home, team_id 1) vs Synthetic FC 2 (away, team_id 2), 2026-10-01, 18:00, final score 1-2.",
    "On-target shots for home team (team_id 1): 6 shots (1 goal, 5 saved). Summary, events (moment/period/minute/second) and map (locations) views retrieved.",
    "Data is synthetic (1 Hz tracking, toy xG). No analysis or dashboard construction performed; original evidence delivered."
  ],
  "status": "complete"
}
```

### Finalización propuesta por el modelo

```json
{
  "clarification": null,
  "evidence_ids": [
    "e1",
    "e2",
    "e3",
    "e4",
    "e5",
    "e6",
    "e7"
  ],
  "notes": [
    "Match resolved: match_id 900001, Synthetic FC 1 (home, team_id 1) vs Synthetic FC 2 (away, team_id 2), 2026-10-01, 18:00, final score 1-2.",
    "On-target shots for home team (team_id 1): 6 shots (1 goal, 5 saved). Summary, events (moment/period/minute/second) and map (locations) views retrieved.",
    "Data is synthetic (1 Hz tracking, toy xG). No analysis or dashboard construction performed; original evidence delivered."
  ],
  "status": "complete"
}
```

## Salida original

[Output completo del agente, con evidencia MCP sin reemplazar cifras](output.json)

### e1: find_entities

```json
{
  "total": 1
}
```

### e2: find_entities

```json
{
  "total": 1
}
```

### e3: list_matches

```json
{
  "total": 1
}
```

### e4: get_match_context

```json
{
  "match": {
    "match_id": 900001,
    "match_date": "2026-10-01",
    "kick_off": "18:00:00",
    "home_score": 1,
    "away_score": 2,
    "competition_id": 900,
    "season_id": 2026,
    "competition_name": "Synthetic Demo League",
    "season_name": "2026 synthetic",
    "generator_version": "3.0.0",
    "is_synthetic": true,
    "data_kind": null,
    "provider": null,
    "match_date_known": true,
    "home_team_id": 1,
    "home_team_name": "Synthetic FC 1",
    "away_team_id": 2,
    "away_team_name": "Synthetic FC 2"
  }
}
```

### e5: get_shots

```json
{
  "total": 6,
  "summary": {
    "shots": 6,
    "goals": 1,
    "shots_on_target": 6,
    "xg": 0.6060797022686976,
    "xg_per_shot": 0.10101328371144959,
    "goals_minus_xg": 0.39392029773130244,
    "conversion_rate": 0.16666666666666666,
    "on_target_rate": 1.0,
    "outcomes": {
      "Saved": 5,
      "Goal": 1
    },
    "body_parts": {
      "Right Foot": 3,
      "Head": 2,
      "Left Foot": 1
    }
  }
}
```

| Evento | Período | Reloj del período | X | Y | Resultado |
|---|---:|---|---:|---:|---|

Coordenadas de eventos 120×80, relativas al equipo actuante; conservar la procedencia sintética de este partido.

### e6: get_shots

```json
{
  "total": 6,
  "summary": {
    "shots": 6,
    "goals": 1,
    "shots_on_target": 6,
    "xg": 0.6060797022686976,
    "xg_per_shot": 0.10101328371144959,
    "goals_minus_xg": 0.39392029773130244,
    "conversion_rate": 0.16666666666666666,
    "on_target_rate": 1.0,
    "outcomes": {
      "Saved": 5,
      "Goal": 1
    },
    "body_parts": {
      "Right Foot": 3,
      "Head": 2,
      "Left Foot": 1
    }
  }
}
```

| Evento | Período | Reloj del período | X | Y | Resultado |
|---|---:|---|---:|---:|---|
| a49e1ca5-368f-8b36-8aec-8071e3a8e27b | 1 | 00:04:49.000 | 89.10734138312901 | 67.90624259155072 | {'id': 100, 'name': 'Saved'} |
| d63e70ab-2391-848b-8981-8c5ed4e9b48c | 1 | 00:19:25.000 | 101.22514954814726 | 46.15688025856757 | {'id': 100, 'name': 'Saved'} |
| fac23d74-f8bc-8bca-8ba1-300eebd8d028 | 1 | 00:22:02.000 | 104.6951018896019 | 43.76424993274938 | {'id': 97, 'name': 'Goal'} |
| b277f460-3155-8969-8cb8-72ed88c1fe39 | 1 | 00:27:03.000 | 96.92154243180924 | 8.310561748324716 | {'id': 100, 'name': 'Saved'} |
| 079c3b10-7cd2-8902-83d9-ebcc3b8a85ea | 1 | 00:34:30.000 | 104.57266920692682 | 72.30495867624234 | {'id': 100, 'name': 'Saved'} |
| a2e0a0ad-ce62-8e17-8e63-beb8ef3f03dc | 2 | 00:23:19.000 | 104.20686765479374 | 34.78333258068301 | {'id': 100, 'name': 'Saved'} |

Coordenadas de eventos 120×80, relativas al equipo actuante; conservar la procedencia sintética de este partido.

### e7: get_shots

```json
{
  "total": 6,
  "summary": {
    "shots": 6,
    "goals": 1,
    "shots_on_target": 6,
    "xg": 0.6060797022686976,
    "xg_per_shot": 0.10101328371144959,
    "goals_minus_xg": 0.39392029773130244,
    "conversion_rate": 0.16666666666666666,
    "on_target_rate": 1.0,
    "outcomes": {
      "Saved": 5,
      "Goal": 1
    },
    "body_parts": {
      "Right Foot": 3,
      "Head": 2,
      "Left Foot": 1
    }
  }
}
```

| Evento | Período | Reloj del período | X | Y | Resultado |
|---|---:|---|---:|---:|---|
| a49e1ca5-368f-8b36-8aec-8071e3a8e27b | 1 | 00:04:49.000 | 89.10734138312901 | 67.90624259155072 | {'id': 100, 'name': 'Saved'} |
| d63e70ab-2391-848b-8981-8c5ed4e9b48c | 1 | 00:19:25.000 | 101.22514954814726 | 46.15688025856757 | {'id': 100, 'name': 'Saved'} |
| fac23d74-f8bc-8bca-8ba1-300eebd8d028 | 1 | 00:22:02.000 | 104.6951018896019 | 43.76424993274938 | {'id': 97, 'name': 'Goal'} |
| b277f460-3155-8969-8cb8-72ed88c1fe39 | 1 | 00:27:03.000 | 96.92154243180924 | 8.310561748324716 | {'id': 100, 'name': 'Saved'} |
| 079c3b10-7cd2-8902-83d9-ebcc3b8a85ea | 1 | 00:34:30.000 | 104.57266920692682 | 72.30495867624234 | {'id': 100, 'name': 'Saved'} |
| a2e0a0ad-ce62-8e17-8e63-beb8ef3f03dc | 2 | 00:23:19.000 | 104.20686765479374 | 34.78333258068301 | {'id': 100, 'name': 'Saved'} |

Coordenadas de eventos 120×80, relativas al equipo actuante; conservar la procedencia sintética de este partido.

## Alcance de la ejecución

9 turnos del modelo; 7 llamadas MCP; 145036 tokens reportados.

El agente propone llamadas MCP parametrizadas. El servidor ejecuta consultas y cálculos predefinidos; no se genera SQL libre. Esta traza muestra acciones y resultados observables, sin razonamiento interno ni credenciales.

## Comprobación independiente

Las siete respuestas se cotejaron contra llamadas directas al MCP: [ver validación](validation.json). El hash del prompt guardado coincide con el registrado al iniciar la ejecución.

## Repetir la demostración

Desde la raíz, con la sesión CLI y MCP configurados:

```powershell
$env:PYTHONPATH = "src"
.venv/Scripts/python.exe scripts/demo_data_agent.py --match-id 900001 --output-dir docs/examples/agent-demo-nueva
```

El script lee `.env.local` sin imprimir credenciales, conserva el prompt utilizado y muestra cada llamada mientras se ejecuta. La carpeta de salida debe ser nueva.
