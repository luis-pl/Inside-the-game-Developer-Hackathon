"""Language preferences shared by agents; machine contracts stay untranslated."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

Language = Literal["es", "en", "pt", "fr", "it", "de"]


@lru_cache(maxsize=6)
def messages(language: Language = "es") -> dict[str, str]:
    if language not in {"es", "en", "pt", "fr", "it", "de"}:
        raise ValueError("UNSUPPORTED_LANGUAGE")
    return json.loads(
        (Path(__file__).with_name("locales") / f"{language}.json").read_text(
            encoding="utf-8"
        )
    )


def wording(key: str, language: Language = "es") -> str:
    return messages(language)[key]
