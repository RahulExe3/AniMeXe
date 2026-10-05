from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import load_config
from .logging import configure_logging
from .metadata import MetadataService
from .models import AnimeRecord, EpisodeRecord
from .paths import ProjectPaths
from .scheduler import Scheduler
from .state import StateStore


def _project_paths() -> ProjectPaths:
    paths = ProjectPaths.discover()
    paths.ensure()
    return paths


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="animexe",
        description="AniMeXe anime episode automation engine",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="logging level (default: INFO)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="create the canonical AniMeXe directories and state files")
    sub.add_parser("status", help="show current persisted state")

    anime = sub.add_parser("anime", help="manage anime records")
    anime_sub = anime.add_subparsers(dest="anime_command", required=True)
    anime_sub.add_parser("list", help="list anime records")

    add_anime = anime_sub.add_parser("add", help="add one anime record")
    add_anime.add_argument("id")
    add_anime.add_argument("title")
    add_anime.add_argument("--season", type=int, default=1)
    add_anime.add_argument("--priority", type=int, default=0)

    episode = sub.add_parser("episode", help="inspect episode records")
    episode_sub = episode.add_subparsers(dest="episode_command", required=True)
    episode_list = episode_sub.add_parser("list", help="list episodes")
    episode_list.add_argument("--anime-id")

    sub.add_parser("plan", help="show the scheduler's next job plan")

    metadata = sub.add_parser("metadata", help="query normalized anime metadata")
    metadata_sub = metadata.add_subparsers(dest="metadata_command", required=True)

    metadata_search = metadata_sub.add_parser("search", help="search anime metadata")
    metadata_search.add_argument("query")
    metadata_search.add_argument("--limit", type=int, default=None)

    metadata_get = metadata_sub.add_parser("get", help="fetch one anime by metadata provider id")
    metadata_get.add_argument("provider", choices=("anilist", "jikan"))
    metadata_get.add_argument("id")

    return parser


def _print_json(value: object) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)

    paths = _project_paths()
    store = StateStore(paths.data)

    if args.command == "init":
        store.ensure()
        print(f"Initialized AniMeXe at {paths.root}")
        return

    if args.command == "status":
        anime = store.list_anime()
        episodes = store.list_episodes()
        scheduler = store.load_scheduler()
        _print_json(
            {
                "root": str(paths.root),
                "anime": len(anime),
                "episodes": len(episodes),
                "active_anime": sum(item.active for item in anime),
                "successful_outputs_today": scheduler.successful_outputs_today,
                "daily_output_limit": scheduler.daily_output_limit,
                "strategy": scheduler.strategy,
            }
        )
        return

    if args.command == "anime":
        if args.anime_command == "list":
            _print_json([item.__dict__ for item in store.list_anime()])
            return

        if args.anime_command == "add":
            record = AnimeRecord(
                id=args.id,
                title=args.title,
                season=args.season,
                priority=args.priority,
                status="DISCOVERED",
                release_state="NOT_YET_RELEASED",
            )
            store.save_anime(record)
            print(f"Added anime: {record.title} (S{record.season})")
            return

    if args.command == "episode":
        if args.episode_command == "list":
            _print_json(
                [item.__dict__ for item in store.list_episodes(args.anime_id)]
            )
            return

    if args.command == "plan":
        scheduler_state = store.load_scheduler()
        planner = Scheduler(scheduler_state)
        plans = planner.plan(store.list_anime(), store.list_episodes())
        _print_json([plan.__dict__ for plan in plans])
        return

    if args.command == "metadata":
        config_path = paths.config / "config.yml"
        if not config_path.exists():
            config_path = paths.config / "config.example.yml"
        app_config = load_config(config_path)
        service = MetadataService.create(
            anilist_endpoint=app_config.metadata.anilist_endpoint,
            jikan_base_url=app_config.metadata.jikan_base_url,
        )

        if args.metadata_command == "search":
            limit = args.limit or app_config.metadata.search_limit
            results = service.search(args.query, limit=limit)
            _print_json([
                {
                    "provider": result.provider,
                    "error": result.error,
                    "metadata": (
                        None
                        if result.metadata is None
                        else {
                            key: value
                            for key, value in result.metadata.__dict__.items()
                            if key != "raw"
                        }
                    ),
                }
                for result in results
            ])
            return

        if args.metadata_command == "get":
            metadata = service.get_anime(args.provider, args.id)
            _print_json({
                key: value
                for key, value in metadata.__dict__.items()
                if key != "raw"
            })
            return

    parser.error("unsupported command")
