#!/usr/bin/env python3
"""Full-refresh loader for map resource CSV data."""
import argparse
import logging
import sys
from pathlib import Path
from typing import Iterable, Tuple

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env", override=True)

from config import Config
from sanbot.db import get_connection


def _load_config() -> dict:
    cfg_obj = Config()
    keys = [
        "MYSQL_HOST",
        "MYSQL_PORT",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_DB",
    ]
    return {key: getattr(cfg_obj, key) for key in keys}


def _parse_maps(maps_dir: Path) -> Tuple[list[Tuple[str, str, str, int, int, str]], dict]:
    rows: list[Tuple[str, str, str, int, int, str]] = []
    stats = {"file_count": 0, "row_count": 0, "skipped": 0, "errors": []}

    for csv_path in sorted(maps_dir.glob("*.csv")):
        stats["file_count"] += 1
        scenario = csv_path.stem
        try:
            df = pd.read_csv(csv_path, dtype=str, encoding="utf-8-sig")
        except Exception as exc:  # noqa: BLE001
            stats["errors"].append(f"读取失败 {csv_path.name}: {exc}")
            continue

        expected = {"所属郡", "等级", "X", "Y"}
        if not expected.issubset(set(df.columns)):
            stats["errors"].append(f"缺少必要列 {csv_path.name}")
            continue

        df = df.fillna("")
        for _, row in df.iterrows():
            prefecture = str(row.get("所属郡", "")).strip()
            resource_level = str(row.get("等级", "")).strip()
            x_raw = str(row.get("X", "")).strip()
            y_raw = str(row.get("Y", "")).strip()

            if not prefecture or not resource_level or not x_raw or not y_raw:
                stats["skipped"] += 1
                continue

            try:
                coord_x = int(float(x_raw))
                coord_y = int(float(y_raw))
            except ValueError:
                stats["skipped"] += 1
                continue

            rows.append((scenario, prefecture, resource_level, coord_x, coord_y, csv_path.name))
            stats["row_count"] += 1

    return rows, stats


def _sync(rows: Iterable[Tuple[str, str, str, int, int, str]], cfg: dict) -> None:
    rows = list(rows)
    if not rows:
        return

    conn = get_connection(cfg)
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE map_resources")
            cur.executemany(
                """
                INSERT INTO map_resources (
                    scenario, prefecture, resource_level, coord_x, coord_y, source_file
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync map resource CSVs into database.")
    default_dir = Path(__file__).resolve().parent.parent / "maps"
    parser.add_argument("--maps-dir", type=Path, default=default_dir, help="Directory holding map CSV files")
    parser.add_argument("--dry-run", action="store_true", help="Parse files without writing database changes")
    args = parser.parse_args()

    maps_dir = args.maps_dir.resolve()
    if not maps_dir.is_dir():
        logging.error("Maps directory %s does not exist", maps_dir)
        return 1

    rows, stats = _parse_maps(maps_dir)

    if stats["errors"]:
        for message in stats["errors"]:
            logging.error(message)

    logging.info(
        "Parsed %d rows from %d files (skipped %d)",
        stats["row_count"],
        stats["file_count"],
        stats["skipped"],
    )

    if not rows:
        logging.warning("No rows available for sync")
        return 2

    if args.dry_run:
        logging.info("Dry run mode enabled, skipping database sync")
        return 0

    cfg = _load_config()
    _sync(rows, cfg)
    logging.info("Synced %d rows into map_resources", len(rows))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
