"""Fetch eight distinct, pinned SkillCorner open matches, including LFS data."""

import concurrent.futures
import hashlib
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache/skillcorner"
MANIFEST = ROOT / "database/azure-sql/skillcorner-source.json"
REPO = "SkillCorner/opendata"


def get(url):
    with urlopen(
        Request(url, headers={"User-Agent": "inside-game-data-import"}), timeout=180
    ) as response:
        return response.read()


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    pinned = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else None
    revision = (
        pinned["revision"]
        if pinned
        else json.loads(get(f"https://api.github.com/repos/{REPO}/commits/master"))[
            "sha"
        ]
    )
    matches = json.loads(
        get(f"https://raw.githubusercontent.com/{REPO}/{revision}/data/matches.json")
    )
    ids = pinned["match_ids"] if pinned else [m["id"] for m in matches[:8]]

    def fetch(item):
        mid, suffix = item
        name = f"{mid}_{suffix}"
        relative = f"data/matches/{mid}/{name}"
        raw = f"https://raw.githubusercontent.com/{REPO}/{revision}/{relative}"
        url = raw
        expected = None
        if suffix.endswith("jsonl"):
            pointer = get(raw).decode()
            expected = re.search(r"oid sha256:([a-f0-9]+)", pointer)[1]
            url = f"https://media.githubusercontent.com/media/{REPO}/{revision}/{relative}"
        target = CACHE / name
        if not target.exists():
            data = get(url)
            if expected:
                assert hashlib.sha256(data).hexdigest() == expected, (
                    "LFS checksum mismatch"
                )
            target.write_bytes(data)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if expected:
            assert digest == expected
        if pinned:
            assert digest == next(
                f["sha256"] for f in pinned["files"] if f["file"] == name
            )
        print(
            json.dumps({"match": mid, "file": suffix, "bytes": target.stat().st_size}),
            flush=True,
        )
        return {
            "source_match_id": mid,
            "file": name,
            "url": url,
            "sha256": digest,
            "bytes": target.stat().st_size,
        }

    jobs = [
        (mid, s)
        for mid in ids
        for s in (
            "match.json",
            "dynamic_events.csv",
            "phases_of_play.csv",
            "tracking_extrapolated.jsonl",
        )
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        files = list(executor.map(fetch, jobs))
    license_text = get(
        f"https://raw.githubusercontent.com/{REPO}/{revision}/LICENSE"
    ).decode()
    (ROOT / "database/azure-sql/SKILLCORNER-LICENSE.txt").write_text(
        license_text, encoding="utf-8"
    )
    result = {
        "provider": "SkillCorner",
        "repository": f"https://github.com/{REPO}",
        "revision": revision,
        "license": "MIT; see SKILLCORNER-LICENSE.txt",
        "data_kind": "real_pseudonymized",
        "is_synthetic": False,
        "source_hz": 10,
        "match_ids": ids,
        "files": files,
    }
    MANIFEST.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "matches": len(ids),
                "bytes": sum(f["bytes"] for f in files),
                "status": "downloaded",
            }
        )
    )


if __name__ == "__main__":
    main()
