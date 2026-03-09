from __future__ import annotations

import csv
import json
from pathlib import Path

import requests

BASE = Path('/Users/sid/Desktop/PokeHunter/backend')
MAP_CSV = BASE / 'dataset_comp_set_ids.csv'
OUT_SQL = BASE / 'sets_from_dataset.sql'
OUT_REPORT = BASE / 'dataset_set_resolution_report.csv'

# Normalize IDs inferred from filenames/folders into TCGdex IDs.
ID_ALIASES = {
    'ann25th': 'cel25',
    'ann25thr': 'cel25',
    'col': 'col1',
    'cp': 'swsh3.5',
    'cz': 'swsh12.5',
    'ex06': 'ex6',
    'ex08': 'ex8',
    'gum': 'det1',
    'me1': 'me01',
    'mebsp': 'mep',
    'sv1': 'sv01',
    'sv2': 'sv02',
    'sv3': 'sv03',
    'sv3-5': 'sv03.5',
    'sv4': 'sv04',
    'sv4-5': 'sv04.5',
    'sv5': 'sv05',
    'sv6': 'sv06',
    'sv6-5': 'sv06.5',
    'sv7': 'sv07',
    'sv8': 'sv08',
    'sv8-5': 'sv08.5',
    'sv9': 'sv09',
    'sv10-5': 'sv10.5',
    'zsv10-5': 'sv10.5b',
    'svbsp': 'svp',
    'tatm': 'dc1',
}

# Folder-level overrides when filename-derived IDs are missing or noisy.
FOLDER_OVERRIDES = {
    'box-topper': None,
    'expedition': 'ecard1',
    'hs-energy-2010-unnumbered': None,
    'miscellaneous': None,
    'rumble': 'ru1',
    'black-bolt': 'sv10.5b',
    'scarlet-violet-energy': None,
}


def normalize_id(raw: str | None, folder: str) -> str | None:
    if folder in FOLDER_OVERRIDES:
        return FOLDER_OVERRIDES[folder]
    if not raw:
        return None
    value = raw.strip().lower()
    return ID_ALIASES.get(value, value)


def load_tcgdex_sets() -> tuple[list[dict], dict[str, dict]]:
    r = requests.get('https://api.tcgdex.net/v2/en/sets', timeout=30)
    r.raise_for_status()
    sets = r.json()
    idx = {str(s.get('id', '')).lower(): s for s in sets}
    return sets, idx


def fetch_release_date(set_id: str) -> str | None:
    r = requests.get(f'https://api.tcgdex.net/v2/en/sets/{set_id}', timeout=30)
    if r.status_code != 200:
        return None
    data = r.json()
    rd = data.get('releaseDate')
    return rd if isinstance(rd, str) and rd else None


def sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def main() -> None:
    ordered_sets, tcgdex_index = load_tcgdex_sets()

    rows = []
    with MAP_CSV.open(newline='', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            folder = row['folder'].strip()
            raw_id = (row.get('set_id') or '').strip()
            resolved_id = normalize_id(raw_id or None, folder)

            status = 'resolved' if resolved_id and resolved_id.lower() in tcgdex_index else 'unresolved'
            rows.append(
                {
                    'folder': folder,
                    'raw_set_id': raw_id,
                    'resolved_set_id': resolved_id or '',
                    'status': status,
                }
            )

    with OUT_REPORT.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=['folder', 'raw_set_id', 'resolved_set_id', 'status'],
        )
        writer.writeheader()
        writer.writerows(rows)

    used_ids = {r['resolved_set_id'].lower() for r in rows if r['status'] == 'resolved'}

    ordered_used = []
    for s in ordered_sets:
        sid = str(s.get('id', '')).lower()
        if sid in used_ids:
            ordered_used.append(sid)

    values_sql = []
    unresolved = [r for r in rows if r['status'] != 'resolved']

    for sid in ordered_used:
        set_obj = tcgdex_index[sid]
        name = str(set_obj.get('name', '')).strip()
        if not name:
            continue
        release_date = fetch_release_date(sid)

        if release_date:
            values_sql.append(
                f"({sql_quote(sid)}, {sql_quote(name)}, {sql_quote(release_date)})"
            )
        else:
            values_sql.append(
                f"({sql_quote(sid)}, {sql_quote(name)}, NULL)"
            )

    lines = []
    lines.append('-- Generated from dataset_comp folder mapping + TCGdex set metadata')
    lines.append('-- Source order preserved from: GET https://api.tcgdex.net/v2/en/sets')
    lines.append('')

    if values_sql:
        lines.append('INSERT INTO sets (id, name, release_date)')
        lines.append('VALUES')
        lines.append(',\n'.join(values_sql))
        lines.append('ON CONFLICT (id) DO UPDATE SET')
        lines.append('  name = EXCLUDED.name,')
        lines.append('  release_date = EXCLUDED.release_date;')
        lines.append('')

    lines.append(f'-- Resolved sets: {len(values_sql)}')
    lines.append(f'-- Unresolved folders: {len(unresolved)}')
    for r in unresolved:
        lines.append(
            f"-- unresolved folder={r['folder']} raw_set_id={r['raw_set_id'] or '(none)'}"
        )

    OUT_SQL.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    print(f'Wrote {OUT_SQL}')
    print(f'Wrote {OUT_REPORT}')
    print(f'Resolved sets: {len(values_sql)}')
    print(f'Unresolved folders: {len(unresolved)}')


if __name__ == '__main__':
    main()
