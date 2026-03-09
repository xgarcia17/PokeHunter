from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET_NAME = "pokemon-images"
LOCAL_ROOT = Path("identification/dataset_comp")
TIMEOUT_SECONDS = 60
MAX_WORKERS = int(os.getenv("UPLOAD_WORKERS", "12"))


def validate_env() -> None:
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_SERVICE_ROLE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


def list_webp_files(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(f"Local folder not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".webp":
            files.append(path)
    return sorted(files)


def upload_one_file(local_file: Path, root: Path) -> str:
    object_path = local_file.relative_to(root).as_posix()
    endpoint = f"{SUPABASE_URL}/storage/v1/object/{BUCKET_NAME}/{object_path}"
    headers = {
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Content-Type": "image/webp",
        "x-upsert": "false",
    }

    with local_file.open("rb") as fh:
        response = requests.post(endpoint, headers=headers, data=fh, timeout=TIMEOUT_SECONDS)

    if 200 <= response.status_code < 300:
        print(f"UPLOADED: {object_path}")
        return "uploaded"

    body_lower = response.text.lower()
    if response.status_code in (400, 409) and "exist" in body_lower:
        print(f"SKIPPED (already exists): {object_path}")
        return "skipped"

    print(f"FAILED: {object_path} | {response.status_code} | {response.text}")
    return "failed"


def main() -> None:
    validate_env()
    files = list_webp_files(LOCAL_ROOT)

    total = len(files)
    uploaded = 0
    skipped = 0
    failed = 0

    workers = max(1, min(MAX_WORKERS, total if total > 0 else 1))
    print(f"Found {total} .webp files under: {LOCAL_ROOT}")
    print(f"Using {workers} parallel workers")

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_file = {
            executor.submit(upload_one_file, local_file, LOCAL_ROOT): local_file for local_file in files
        }
        for future in as_completed(future_to_file):
            local_file = future_to_file[future]
            try:
                result = future.result()
                if result == "uploaded":
                    uploaded += 1
                elif result == "skipped":
                    skipped += 1
                else:
                    failed += 1
            except Exception as exc:
                failed += 1
                object_path = local_file.relative_to(LOCAL_ROOT).as_posix()
                print(f"FAILED: {object_path} | exception: {exc}")

    print("\nSummary")
    print(f"total files found: {total}")
    print(f"uploaded: {uploaded}")
    print(f"skipped: {skipped}")
    print(f"failed: {failed}")


if __name__ == "__main__":
    main()
