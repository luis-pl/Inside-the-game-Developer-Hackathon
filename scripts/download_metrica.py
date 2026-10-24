"""Download official, already anonymized Metrica samples without credentials."""

import concurrent.futures
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "metrica"
REPOSITORY = "metrica-sports/sample-data"


def download_samples():
    manifest_path = ROOT / "database/azure-sql/metrica-source.json"
    pinned = json.loads(manifest_path.read_text()) if manifest_path.exists() else None
    if pinned:
        revision = pinned["revision"]
    else:
        request = Request(
            f"https://api.github.com/repos/{REPOSITORY}/commits/master",
            headers={"User-Agent": "inside-game-data-import"},
        )
        with urlopen(request, timeout=60) as response:
            revision = json.load(response)["sha"]
    CACHE.mkdir(parents=True, exist_ok=True)
    files = []
    for game in (1, 2):
        for suffix in (
            "RawEventsData.csv",
            "RawTrackingData_Home_Team.csv",
            "RawTrackingData_Away_Team.csv",
        ):
            name = f"Sample_Game_{game}_{suffix}"
            files.append(
                (
                    game,
                    name,
                    f"https://raw.githubusercontent.com/{REPOSITORY}/{revision}/data/Sample_Game_{game}/{name}",
                )
            )

    def fetch(item):
        game, name, url = item
        target = CACHE / name
        if not target.exists():
            with urlopen(url, timeout=120) as response:
                data = response.read()
            target.write_bytes(data)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if pinned:
            expected = next(f for f in pinned["files"] if f["file"] == name)
            assert digest == expected["sha256"], (
                f"Checksum mismatch for pinned source {name}"
            )
        return {
            "game": game,
            "file": name,
            "url": url,
            "sha256": digest,
            "bytes": target.stat().st_size,
        }

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(fetch, files))
    manifest = {
        "provider": "Metrica Sports",
        "repository": f"https://github.com/{REPOSITORY}",
        "revision": revision,
        "data_kind": "real_anonymized",
        "is_synthetic": False,
        "source_hz": 25,
        "files": results,
    }
    (ROOT / "database/azure-sql/metrica-source.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "downloaded": len(results),
                "bytes": sum(r["bytes"] for r in results),
                "revision": revision,
            }
        )
    )


if __name__ == "__main__":
    download_samples()
