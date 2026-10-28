"""Registro cerrado: el modelo selecciona recetas, no genera componentes."""

import json
from importlib.resources import files
from typing import Literal

CATALOG = json.loads(
    files(__package__).joinpath("catalog.json").read_text(encoding="utf-8")
)
RECIPES = {item["id"]: item for item in CATALOG["insights"]}
InsightId = Literal[tuple(RECIPES)]


def describe(insight_id):
    if insight_id not in RECIPES:
        raise ValueError("UNKNOWN_INSIGHT")
    return RECIPES[insight_id]
