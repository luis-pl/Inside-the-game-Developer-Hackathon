"""Host-owned source annotation masks; never change original evidence values."""

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def profiles():
    path = (
        Path(__file__).resolve().parents[1]
        / "agents/insights_agent/source_profiles.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def profile(evidence):
    provenance = evidence.response.provenance
    providers = {
        d.get("provider")
        for d in provenance.get("datasets", [])
        if isinstance(d, dict) and d.get("provider")
    }
    provider = provenance.get("provider") or (
        next(iter(providers)) if len(providers) == 1 else None
    )
    key = "synthetic" if provenance.get("is_synthetic") is True else provider
    return profiles().get(key, {})


def unannotated(evidence, recipe):
    return set(profile(evidence).get("unannotated_metrics", {}).get(recipe, []))


OPERATION_RECIPES = {
    "get_shots": "shot_map",
    "get_passes": "pass_map",
    "get_defensive_actions": "defensive_actions",
    "get_ball_actions": "ball_progression",
}


def annotated_summary(evidence, summary):
    hidden = unannotated(evidence, OPERATION_RECIPES.get(evidence.operation, ""))
    return {k: v for k, v in summary.items() if k not in hidden}
