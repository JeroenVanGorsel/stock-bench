"""CLI entry points."""

from __future__ import annotations

import argparse
import asyncio
import logging

import uvicorn

from .api import create_app
from .config import get_settings
from .logging_utils import setup_logging
from .orchestrator import MarketOrchestrator
from .storage import SQLiteRepository


logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stock Bench CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("serve", help="Start the web dashboard")
    subparsers.add_parser("seed", help="Bootstrap models and seed tasks")
    subparsers.add_parser("run-round", help="Run a single benchmark round")
    run_batch = subparsers.add_parser("run-batch", help="Run multiple rounds")
    run_batch.add_argument("--count", type=int, default=3)
    subparsers.add_parser("tail-logs", help="Print the log file path for live tailing")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    log_path = setup_logging()
    settings = get_settings()
    repository = SQLiteRepository(settings.database_path)
    orchestrator = MarketOrchestrator(repository)
    logger.info("cli command received | command=%s", args.command)

    if args.command == "serve":
        logger.info("starting dashboard server on http://127.0.0.1:8000")
        uvicorn.run(create_app(), host="127.0.0.1", port=8000)
        return
    if args.command == "seed":
        orchestrator.bootstrap()
        logger.info("seed completed")
        print("Seeded models and tasks")
        return
    if args.command == "run-round":
        result = asyncio.run(orchestrator.run_one_round())
        print(result.to_dict())
        return
    if args.command == "run-batch":
        results = asyncio.run(orchestrator.run_batch(args.count))
        print({"count": len(results)})
        return
    if args.command == "tail-logs":
        print(log_path)
        return
    parser.error("Unknown command")


if __name__ == "__main__":
    main()
