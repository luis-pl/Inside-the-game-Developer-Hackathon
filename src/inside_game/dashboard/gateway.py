"""Anti-corruption layer: only predefined, read-only operations are allowed."""

import json
import math
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .config import DashboardConfig


class DataError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


class Operations(Protocol):
    def execute(self, operation: str, arguments: dict) -> dict: ...


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class HttpOperations:
    ALLOWED = frozenset(
        {
            "list_matches",
            "get_match_context",
            "get_tracking_window",
            "get_events",
            "get_passes",
        }
    )

    def __init__(self, config: DashboardConfig):
        self.config = config
        self.client = build_opener(NoRedirects())

    def execute(self, operation, arguments):
        if operation not in self.ALLOWED:
            raise DataError("Operación no permitida.", 400)
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"
        request = Request(
            f"{self.config.api_url}/api/operations/{operation}",
            data=json.dumps(arguments).encode(),
            headers=headers,
            method="POST",
        )
        try:
            with self.client.open(request, timeout=35) as response:
                payload = response.read(1_048_577)
            if len(payload) > 1_048_576:
                raise DataError("Respuesta demasiado grande; reduce la ventana.")
            return json.loads(payload)
        except HTTPError as error:
            messages = {
                401: "Falta una clave válida: configura INSIDE_GAME_API_KEY en el .env del servidor.",
                403: "La credencial no tiene permiso para esta consulta.",
                422: "La fuente no contiene los campos o la cobertura necesarios para esta consulta.",
                429: "Límite de consultas alcanzado. Espera un minuto.",
                503: "Azure está iniciando o temporalmente no disponible. Reintenta.",
            }
            raise DataError(
                messages.get(
                    error.code,
                    "La API rechazó la consulta. Comprueba partido, período y ventana.",
                ),
                error.code if error.code in messages else 502,
            ) from None
        except (URLError, TimeoutError, json.JSONDecodeError):
            raise DataError(
                "No se pudo obtener una respuesta válida de Azure. Reintenta."
            ) from None


def match_view(row):
    teams = [
        {"id": row[f"{side}_team_id"], "name": row[f"{side}_team_name"]}
        for side in ("home", "away")
    ]
    return {
        "id": row["match_id"],
        "label": f"{teams[0]['name']} vs {teams[1]['name']}",
        "teams": teams,
        "dataKind": "synthetic"
        if row.get("is_synthetic", True)
        else row.get("data_kind") or "real_anonymized",
    }


class EpisodeService:
    def __init__(self, operations: Operations):
        self.operations = operations

    def matches(self):
        response = self.operations.execute("list_matches", {"limit": 100})
        rows = response["data"]["items"]
        # Real samples are the default catalogue; the old synthetic dataset
        # remains accessible through API/MCP for historical demonstrations.
        real = [row for row in rows if row.get("is_synthetic") is False]
        return [match_view(row) for row in (real or rows)]

    def episode(
        self, match_id, period, start_seconds, duration_seconds=2700, stride_s=1
    ):
        if (
            type(match_id) is not int
            or match_id <= 0
            or period not in (1, 2)
            or type(start_seconds) is not int
            or not 0 <= start_seconds <= 3600
            or type(duration_seconds) is not int
            or not 1 <= duration_seconds <= 2700
            or type(stride_s) is not int
            or stride_s not in (1, 2, 5)
        ):
            raise DataError("Partido, período o segundo inicial inválidos.", 400)
        context = self.operations.execute("get_match_context", {"match_id": match_id})[
            "data"
        ]
        meta = context["match"]
        periods = [p for p in context["periods"] if p["period"] == period]
        if len(periods) != 1:
            raise DataError(
                "Se requiere un único run de tracking para el período.", 422
            )
        selected = periods[0]
        run = (
            next(
                r
                for r in context.get("runs", [])
                if str(r["run_id"]) == str(selected["run_id"])
            )
            if context.get("runs")
            else {}
        )
        real_data = meta.get("is_synthetic") is False
        provider = meta.get("provider") or (
            "Metrica Sports" if real_data else "inside-game-demo"
        )
        data_kind = meta.get("data_kind") or (
            "real_anonymized" if real_data else "synthetic"
        )
        step_ms = (
            200
            if real_data
            and run.get("sample_rate_hz", 1) >= 5
            and duration_seconds <= 300
            and stride_s == 1
            else stride_s * 1000
        )
        run_id = str(selected["run_id"])
        start = start_seconds * 1000
        end = min(
            start + duration_seconds * 1000,
            int(selected["duration_ms"]) // 1000 * 1000,
        )
        if end <= start:
            raise DataError("El inicio está fuera del período.", 400)
        lineups = {p["player_id"]: p for p in context["lineups"]}
        frames, warnings = [], []
        # Each upstream call is capped at 120 s. Disjoint half-open windows
        # preserve sampling phase because 120 is divisible by every stride.
        chunk_ms = 20000 if step_ms == 200 else 120000
        for chunk_start in range(start, end, chunk_ms):
            chunk_end = min(chunk_start + chunk_ms, end)
            response = self.operations.execute(
                "get_tracking_window",
                {
                    "match_id": match_id,
                    "run_id": run_id,
                    "scope": {
                        "kind": "window",
                        "period": period,
                        "start_ms": chunk_start,
                        "end_ms": chunk_end,
                    },
                    **(
                        {"sample_step_ms": 200}
                        if step_ms == 200
                        else {"stride_s": stride_s}
                    ),
                },
            )
            frames.extend(
                self._frame(f, lineups, require_complete=False)
                if real_data
                else self._frame(f, lineups)
                for f in response["data"]["frames"]
            )
            warnings.extend(response.get("warnings", []))
        if not frames:
            raise DataError("La ventana no contiene muestras válidas.", 422)
        if [f["timeMs"] for f in frames] != list(range(start, end, step_ms)):
            raise DataError(
                "El tracking contiene huecos o instantes duplicados; no se interpolan.",
                422,
            )
        # A failed event query must not silently imply no actions occurred.
        warnings = list(dict.fromkeys(warnings))
        if real_data:
            warnings.append(
                f"Fuente: {provider}, partido real con identidades enmascaradas. No se ha impuesto una formación ni generado trayectorias."
            )
            if provider == "SkillCorner":
                warnings.append(
                    "Tracking de retransmisión: incluye posiciones detectadas y extrapoladas por SkillCorner. La fuente puede tener errores de identidad y huecos; no equivale a seguimiento óptico completo."
                )
            incomplete = sum(len(f["players"]) < 22 for f in frames)
            missing_ball = sum(f["ball"] is None for f in frames)
            if incomplete or missing_ball:
                warnings.append(
                    f"Tracking real: {incomplete} muestras con jugadores ausentes y {missing_ball} sin balón. Los huecos permanecen visibles; no se inventan posiciones."
                )
            if step_ms >= 1000:
                warnings.append(
                    "Ventana larga: se selecciona una observación por segundo. Para ver el balón a 5 Hz, carga hasta cinco minutos."
                )
        events = []
        try:
            events = self._events(match_id, period, start, end)
        except DataError:
            warnings.append(
                "No se pudieron consultar acciones; la reproducción contiene sólo tracking."
            )
        view = match_view(meta)
        try:
            passes, pass_warnings = self._completed_passes(
                match_id, period, start, end, lineups
            )
            warnings.extend(pass_warnings)
        except DataError:
            passes = None
            warnings.append(
                "Hodge no disponible: no se pudo obtener la red completa de pases de la ventana."
            )
        return {
            "window": {"startMs": start, "endMs": end, "sampleStepMs": step_ms},
            "frames": frames,
            "teams": view["teams"],
            "source": "azure",
            "dataKind": data_kind,
            "provider": provider,
            "matchLabel": view["label"],
            "period": period,
            "homeAttacksRight": bool(selected["home_attacks_positive_x"]),
            "warnings": warnings,
            "events": events,
            "passes": passes,
        }

    def _events(self, match_id, period, start, end):
        arguments = {
            "match_id": match_id,
            "scope": {
                "kind": "window",
                "period": period,
                "start_ms": start,
                "end_ms": end,
            },
            "limit": 200,
        }
        result, seen, cursors = [], set(), set()
        for _ in range(20):
            response = self.operations.execute("get_events", arguments)
            for event in response["data"]["items"]:
                if event["event_id"] in seen:
                    raise DataError("La paginación de acciones repitió un evento.")
                seen.add(event["event_id"])
                result.append(
                    {"timeMs": event["period_time_ms"], "label": event["type_name"]}
                )
            cursor = response.get("pagination", {}).get("next_cursor")
            if not cursor:
                return sorted(result, key=lambda event: event["timeMs"])
            if cursor in cursors:
                raise DataError("La paginación de acciones no avanza.")
            cursors.add(cursor)
            arguments = {**arguments, "cursor": cursor}
        raise DataError(
            "La ventana supera 4000 acciones; no se usa una lista truncada."
        )

    def _completed_passes(self, match_id, period, start, end, lineups):
        arguments = {
            "match_id": match_id,
            "scope": {
                "kind": "window",
                "period": period,
                "start_ms": start,
                "end_ms": end,
            },
            "outcome": "complete",
            "limit": 200,
        }
        result, warnings, seen, cursors = [], [], set(), set()
        unattributed = 0
        for _ in range(5):
            response = self.operations.execute("get_passes", arguments)
            for event in response["data"]["items"]:
                if event["event_id"] in seen:
                    raise DataError("La paginación de pases repitió un evento.")
                seen.add(event["event_id"])
                sender, target = (
                    event.get("player_id"),
                    (event.get("pass") or {}).get("recipient_player_id"),
                )
                if (event.get("pass") or {}).get("outcome") is not None:
                    raise DataError(
                        "La API devolvió un pase incompleto en la red completada."
                    )
                if (
                    sender not in lineups
                    or target not in lineups
                    or sender == target
                    or lineups[sender]["team_id"] != event["team_id"]
                    or lineups[target]["team_id"] != event["team_id"]
                ):
                    unattributed += 1
                    continue
                result.append(
                    {
                        "id": str(event["event_id"]),
                        "source": sender,
                        "target": target,
                        "teamId": event["team_id"],
                        "timeMs": event["period_time_ms"],
                    }
                )
            cursor = response.get("pagination", {}).get("next_cursor")
            if not cursor:
                if unattributed:
                    warnings.append(
                        f"Hodge: {unattributed} pases omitidos por falta de identidad emisor/receptor válida."
                    )
                return result, warnings
            if cursor in cursors:
                raise DataError("La paginación de pases no avanza.")
            cursors.add(cursor)
            arguments = {**arguments, "cursor": cursor}
        raise DataError(
            "La red supera el límite de 1000 pases; no se calcula sobre una muestra truncada."
        )

    @staticmethod
    def _frame(frame, lineups, require_complete=True):
        valid = [
            p
            for p in frame["players"]
            if p["is_on_pitch"]
            and p["position_status"] == "available"
            and all(
                isinstance(p[k], (int, float)) and math.isfinite(p[k])
                for k in ("x_m", "y_m")
            )
        ]
        if (
            (require_complete and len(valid) != 22)
            or len(valid) > 22
            or len({p["player_id"] for p in valid}) != len(valid)
            or any(
                not (
                    (0 if require_complete else -5)
                    <= p["x_m"]
                    <= (105 if require_complete else 110)
                    and (0 if require_complete else -5)
                    <= p["y_m"]
                    <= (68 if require_complete else 73)
                )
                for p in valid
            )
        ):
            raise DataError(
                "Se requieren 22 posiciones activas válidas dentro del campo.", 422
            )
        players = [
            {
                "id": p["player_id"],
                "teamId": p["team_id"],
                "x": p["x_m"],
                "y": p["y_m"],
                "number": lineups[p["player_id"]]["jersey_number"],
                "name": lineups[p["player_id"]]["player_name"],
                "goalkeeper": p["on_pitch_slot"] == 1,
            }
            for p in valid
        ]
        ball = frame.get("ball")
        point = (
            {"x": ball["x_m"], "y": ball["y_m"]}
            if ball
            and ball.get("position_status") == "available"
            and all(
                isinstance(ball.get(k), (int, float)) and math.isfinite(ball[k])
                for k in ("x_m", "y_m")
            )
            else None
        )
        return {
            "timeMs": frame["period_time_ms"],
            "ballInPlay": bool(frame["ball_in_play"]),
            "ball": point,
            "players": players,
        }
