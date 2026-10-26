"""Lectura de la configuración privada del repo (.env.local)."""

import os

from inside_game.local_env import load_local_env, local_setting


def test_load_copies_only_prefixed_assignments_without_overriding(
    tmp_path, monkeypatch
):
    (tmp_path / ".env.local").write_text(
        "# INSIDE_GAME_COMMENTED=no\n"
        "INSIDE_GAME_OPENCODE_MODEL=beam-free\n"
        'INSIDE_GAME_OPENCODE_API_KEY="secret"\n'
        "INSIDE_GAME_MODEL_PROVIDER=opencode-go\n"
        "AZURE_OPENAI_API_KEY=not-copied\n",
        encoding="utf-8",
    )
    # Entorno aislado: lo que escriba load_local_env no debe llegar a otros tests.
    monkeypatch.setattr(os, "environ", {"INSIDE_GAME_MODEL_PROVIDER": "kept"})
    load_local_env(tmp_path)
    assert os.environ["INSIDE_GAME_OPENCODE_MODEL"] == "beam-free"
    assert os.environ["INSIDE_GAME_OPENCODE_API_KEY"] == "secret"
    # El entorno manda: no se pisa lo ya definido.
    assert os.environ["INSIDE_GAME_MODEL_PROVIDER"] == "kept"
    assert "INSIDE_GAME_COMMENTED" not in os.environ
    assert "AZURE_OPENAI_API_KEY" not in os.environ
    assert local_setting("INSIDE_GAME_OPENCODE_MODEL", tmp_path) == "beam-free"
