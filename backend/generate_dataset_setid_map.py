from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from urllib.request import urlopen

DATASET_ROOT = Path("/Users/sid/Desktop/PokeHunter/backend/identification/dataset_comp/raw_images")
OUT_CSV = Path("/Users/sid/Desktop/PokeHunter/backend/dataset_comp_set_ids.csv")
OUT_JSON = Path("/Users/sid/Desktop/PokeHunter/backend/dataset_comp_set_ids.json")


def slugify(value: str) -> str:
    value = value.lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


def extract_ids_from_filename(name: str) -> list[str]:
    found: list[str] = []
    lower = name.lower()

    m = re.match(r"^([a-z0-9.-]+)_en_", lower)
    if m:
        found.append(m.group(1))

    for m2 in re.finditer(r"\b(swsh\d+(?:\.\d+)?)\b", lower):
        found.append(m2.group(1))

    for m3 in re.finditer(r"\b(sv\d+(?:-\d+(?:\.\d+)?)?)\b", lower):
        found.append(m3.group(1))

    # example: en_US-SWSH2-047-...
    m4 = re.search(r"en_us-([a-z0-9.]+)-", lower)
    if m4:
        found.append(m4.group(1))

    # de-duplicate while preserving order
    out: list[str] = []
    for item in found:
        if item not in out:
            out.append(item)
    return out


def load_tcgdex_sets() -> list[dict]:
    with urlopen("https://api.tcgdex.net/v2/en/sets", timeout=30) as resp:  # nosec B310
        return json.loads(resp.read().decode("utf-8"))


def build_slug_index(tcgdex_sets: list[dict]) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    for item in tcgdex_sets:
        sid = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        if not sid or not name:
            continue
        key = slugify(name)
        index.setdefault(key, []).append(sid)
    return index


def main() -> None:
    if not DATASET_ROOT.exists():
        raise FileNotFoundError(f"Dataset root not found: {DATASET_ROOT}")

    tcgdex_sets = load_tcgdex_sets()
    slug_index = build_slug_index(tcgdex_sets)

    rows: list[dict[str, str]] = []

    for folder in sorted([p for p in DATASET_ROOT.iterdir() if p.is_dir()]):
        files = sorted(folder.glob("*.webp"))
        counter: Counter[str] = Counter()

        for f in files:
            for sid in extract_ids_from_filename(f.name):
                counter[sid.lower()] += 1

        inferred = ""
        inferred_count = 0
        method = ""
        candidates = ""

        if counter:
            inferred, inferred_count = counter.most_common(1)[0]
            method = "filename"
            candidates = ",".join([f"{k}:{v}" for k, v in counter.most_common(5)])
        else:
            folder_slug = slugify(folder.name)
            matched = slug_index.get(folder_slug, [])
            if len(matched) == 1:
                inferred = matched[0]
                inferred_count = 0
                method = "folder_name_tcgdex"
                candidates = matched[0]
            elif len(matched) > 1:
                inferred = matched[0]
                inferred_count = 0
                method = "folder_name_tcgdex_multi"
                candidates = ",".join(matched)
            else:
                method = "unresolved"

        rows.append(
            {
                "folder": folder.name,
                "files": str(len(files)),
                "set_id": inferred,
                "signal_count": str(inferred_count),
                "method": method,
                "candidates": candidates,
            }
        )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["folder", "files", "set_id", "signal_count", "method", "candidates"],
        )
        writer.writeheader()
        writer.writerows(rows)

    with OUT_JSON.open("w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2)

    resolved = sum(1 for r in rows if r["set_id"])
    unresolved = len(rows) - resolved
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_JSON}")
    print(f"folders: {len(rows)} | resolved: {resolved} | unresolved: {unresolved}")


if __name__ == "__main__":
    main()
