from __future__ import annotations

import argparse
import json
from pathlib import Path

from quant_core.data.sqlite_store import (
    count_bars,
    count_indices,
    import_bars_csv,
    import_indices_csv,
    import_symbol_csv_dir,
    init_database,
)


def build_sqlite_from_workspace(workspace: str | Path, db_path: str | Path | None = None) -> dict:
    root = Path(workspace)
    db = Path(db_path) if db_path else root / "data" / "market_data.sqlite"
    init_database(db)

    imported_symbols = 0
    imported_bars = 0
    symbol_dir = root / "data" / "symbols"
    bars_csv = root / "data" / "bars.csv"
    indices_csv = root / "data" / "indices.csv"

    if symbol_dir.exists():
        imported_symbols = import_symbol_csv_dir(symbol_dir, db)
    elif bars_csv.exists():
        imported_bars = import_bars_csv(bars_csv, db)

    imported_indices = import_indices_csv(indices_csv, db)
    status = {
        "database_path": str(db),
        "imported_symbol_rows": imported_symbols,
        "imported_bars_rows": imported_bars,
        "imported_index_rows": imported_indices,
        "bars_rows": count_bars(db),
        "index_rows": count_indices(db),
    }
    (root / "data" / "sqlite_status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status


def main() -> None:
    parser = argparse.ArgumentParser(description="Build quant_mvp SQLite market-data store from local CSV caches.")
    parser.add_argument("--workspace", default="quant_workspace")
    parser.add_argument("--db-path")
    args = parser.parse_args()
    status = build_sqlite_from_workspace(args.workspace, args.db_path)
    print(json.dumps(status, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
