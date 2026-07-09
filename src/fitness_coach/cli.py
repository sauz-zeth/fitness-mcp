from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import get_db_path
from .service import FitnessCoachService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fitness-coach")
    parser.add_argument("--db", type=Path, default=None, help="SQLite database path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", help="Create or migrate the SQLite database")

    import_parser = subparsers.add_parser("import-seeds", help="Import YAML seed files into SQLite")
    import_parser.add_argument("--seed-dir", type=Path, default=Path("seeds"))

    subparsers.add_parser("serve", help="Run the MCP stdio server")

    context_parser = subparsers.add_parser("startup-context", help="Print startup context as JSON")
    context_parser.add_argument("--indent", type=int, default=2)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    db_path = args.db or get_db_path()
    service = FitnessCoachService(db_path)

    if args.command == "init-db":
        service.init_db()
        print(f"Initialized database at {db_path}")
    elif args.command == "import-seeds":
        service.import_seeds(args.seed_dir)
        print(f"Imported seeds from {args.seed_dir} into {db_path}")
    elif args.command == "startup-context":
        print(json.dumps(service.get_startup_context(), ensure_ascii=False, indent=args.indent))
    elif args.command == "serve":
        from .mcp_server import run

        run(db_path)
