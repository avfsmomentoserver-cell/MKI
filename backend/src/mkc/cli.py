"""MKC command-line interface.

Subcommands (stable signatures — the intelligence wave fills the bodies):

- ``mkc health``: GET /healthz against the API and print the JSON body.
- ``mkc status``: GET /api/v1/status (authenticates with MKC_API_TOKEN).
- ``mkc ingest <path>``: ingest a source into the registry (git repo,
  markdown directory or chatgpt export directory) and run the
  extraction + relationship passes in-process.
- ``mkc search <query>``: search the knowledge registry in-process
  (works without the API running).
- ``mkc report <type>``: generate a registry report and print its path
  plus the top summary lines.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Sequence

import httpx

from mkc import __version__
from mkc.core.config import bootstrap, get_settings

BANNER = f"MKC (Momento Knowledge Core) v{__version__}"

#: Ingestion collectors exist for these source types (the --source-type
#: choices include legacy values that have no collector yet).
_SUPPORTED_SOURCE_TYPES = ("git", "markdown", "chatgpt")


def _configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _api_base_url() -> str:
    """API base URL from settings (env ``MKC_API_BASE_URL``); --base-url overrides at runtime."""
    return _BASE_URL_OVERRIDE[0] or get_settings().mkc_api_base_url


#: Runtime base-url override slot (filled by the --base-url flag).
_BASE_URL_OVERRIDE: list[str | None] = [None]


def cmd_health(args: argparse.Namespace) -> int:
    """Call GET /healthz and print the response body; exit 0/1 on ok/fail."""
    url = f"{_api_base_url()}/healthz"
    try:
        response = httpx.get(url, timeout=5.0)
        print(response.text)
        return 0 if response.status_code == 200 else 1
    except httpx.HTTPError as exc:
        print(f"health check failed: {exc}", file=sys.stderr)
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Call GET /api/v1/status (authenticated) and pretty-print the JSON body."""
    settings = get_settings()
    url = f"{_api_base_url()}/api/v1/status"
    headers = {"Authorization": f"Bearer {settings.mkc_api_token}"} if settings.token_is_configured else {}
    try:
        response = httpx.get(url, headers=headers, timeout=10.0)
        print(json.dumps(response.json(), indent=2, default=str))
        return 0 if response.status_code == 200 else 1
    except (httpx.HTTPError, ValueError) as exc:
        print(f"status check failed: {exc}", file=sys.stderr)
        return 1


def _build_collector(source_type: str, path: Path):
    """Instantiate the collector matching *source_type*; ``None`` when unsupported."""
    if source_type == "git":
        from mkc.intelligence.ingest.git_collector import GitRepoCollector

        return GitRepoCollector(path)
    if source_type == "markdown":
        from mkc.intelligence.ingest.markdown_collector import MarkdownCollector

        return MarkdownCollector(path)
    if source_type == "chatgpt":
        from mkc.intelligence.ingest.chatgpt_importer import ChatGPTImporter

        return ChatGPTImporter(path)
    return None


def _type_counts_by(session, model, column, limit: int = 12) -> list[tuple[str, int]]:
    from sqlalchemy import func, select

    rows = session.execute(
        select(column, func.count()).group_by(column).order_by(func.count().desc()).limit(limit)
    ).all()
    return [(str(key), int(value)) for key, value in rows]


def cmd_ingest(args: argparse.Namespace) -> int:
    """Ingest a source (git repo / markdown dir / chatgpt export dir) into the MKC registry.

    In-process pipeline: collector (Source + Document rows) -> KnowledgeExtractor
    (knowledge objects + entities) -> RelationshipBuilder (typed edges).
    Everything is idempotent (deterministic ids / upserts). The signature
    (path, source_type) is final: keep it.
    """
    started = time.monotonic()
    path = Path(args.path).expanduser().resolve()
    if not path.exists():
        print(f"ingest: path does not exist: {path}", file=sys.stderr)
        return 1

    collector = _build_collector(args.source_type, path)
    if collector is None:
        print(
            f"ingest: no collector for source_type={args.source_type!r} "
            f"(supported: {', '.join(_SUPPORTED_SOURCE_TYPES)})",
            file=sys.stderr,
        )
        return 1

    try:
        from mkc.core.database import get_session_factory
        from mkc.intelligence.parsing.extractor import KnowledgeExtractor
        from mkc.intelligence.parsing.relationships import RelationshipBuilder
        from mkc.models import Entity, EntityRelation, KnowledgeObject

        ingestion = collector.run()
        if ingestion.errors:
            print(f"ingest: {len(ingestion.errors)} per-file error(s) recorded", file=sys.stderr)
            for line in ingestion.errors[:5]:
                print(f"  ! {line}", file=sys.stderr)

        with get_session_factory()() as session:
            # Extract only from the ingested source to avoid cross-source collisions
            source_row = getattr(collector, "_source_row", None)
            source_id = getattr(source_row, "id", None) if source_row else None
            extraction = KnowledgeExtractor().run(session, source_id=source_id)
            if extraction.errors:
                print(f"extract: {len(extraction.errors)} error(s) recorded", file=sys.stderr)
                for line in extraction.errors[:5]:
                    print(f"  ! {line}", file=sys.stderr)
            relationships = RelationshipBuilder().run(session)
            if relationships.errors:
                print(f"relationships: {len(relationships.errors)} error(s) recorded", file=sys.stderr)
                for line in relationships.errors[:5]:
                    print(f"  ! {line}", file=sys.stderr)
            object_types = _type_counts_by(session, KnowledgeObject, KnowledgeObject.type)
            relation_types = _type_counts_by(session, EntityRelation, EntityRelation.rel_type)
            entity_kinds = _type_counts_by(session, Entity, Entity.kind)
            session.commit()
    except Exception as exc:  # noqa: BLE001 - CLI: print and fail closed
        print(f"ingest failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    duration = time.monotonic() - started
    print(f"ingest: {ingestion.repo} ({args.source_type})")
    print(f"  files indexed:        {ingestion.files_indexed}")
    print(f"  documents upserted:   {ingestion.documents_created}")
    print(f"  commits indexed:      {ingestion.commits_indexed}")
    print(
        f"  knowledge objects:    {extraction.objects_created} created, "
        f"{extraction.objects_replaced} replaced (chunks: {extraction.chunks_analyzed})"
    )
    print(f"  entities created:     {extraction.entities_created}")
    print(
        f"  relationship edges:   {relationships.edges_created} created "
        f"({relationships.edges_skipped_existing} already present)"
    )
    if object_types:
        print("  knowledge by type:    " + ", ".join(f"{name}: {count}" for name, count in object_types))
    if entity_kinds:
        print("  entities by kind:     " + ", ".join(f"{name}: {count}" for name, count in entity_kinds))
    if relation_types:
        print("  relations by type:    " + ", ".join(f"{name}: {count}" for name, count in relation_types))
    total_errors = len(ingestion.errors) + len(extraction.errors) + len(relationships.errors)
    print(f"  errors:               {total_errors}")
    print(f"  duration:             {duration:.1f}s")

    try:
        from mkc.api.metrics import metrics

        metrics.observe_ingestion(args.source_type, time.monotonic() - started)
    except Exception:  # noqa: BLE001 - metrics must never break the CLI
        pass
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """Search the knowledge registry in-process (no API server required).

    AND-token search over knowledge objects (or document titles with
    ``--scope documents``). The signature (query, top_k) is final: keep it.
    """
    from mkc.core.database import get_session_factory
    from mkc.intelligence.search import search_documents, search_knowledge

    if not args.query.strip():
        print("search: query must not be empty", file=sys.stderr)
        return 1
    try:
        with get_session_factory()() as session:
            if args.scope == "documents":
                envelope = search_documents(session, args.query, page_size=args.top_k)
            elif args.scope == "all":
                knowledge = search_knowledge(session, args.query, page_size=args.top_k)
                documents = search_documents(session, args.query, page_size=args.top_k)
                envelope = {
                    "query": args.query,
                    "total": knowledge["total"] + documents["total"],
                    "results": list(knowledge["results"]) + list(documents["results"]),
                }
            else:
                envelope = search_knowledge(session, args.query, page_size=args.top_k)
    except ValueError as exc:
        print(f"search: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI: print and fail closed
        print(f"search failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"search {args.query!r}: {envelope['total']} match(es), showing {len(envelope['results'])}")
    for rank, result in enumerate(envelope["results"], start=1):
        state = result.get("lifecycle_state") or ""
        confidence = result.get("confidence")
        bits = [f"{rank}. [{result['kind']}] {result['title'][:90]}"]
        if state:
            bits.append(f"type={result['type']} state={state}")
        if confidence is not None:
            bits.append(f"conf={confidence:.2f}")
        print("   " + " ".join(bits))
        provenance = result.get("provenance") or {}
        location = provenance.get("source_location") or ""
        if location:
            print(f"      at: {location[:120]}")
        snippet = (result.get("snippet") or "").replace("\n", " ")
        print(f"      ~: {snippet[:160]}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Generate a registry report and print its path plus top summary lines."""
    from mkc.core.database import get_session_factory
    from mkc.intelligence.reports.generator import SUPPORTED_REPORT_TYPES, generate_report

    if args.report_type not in SUPPORTED_REPORT_TYPES:
        print(
            f"report: unknown type {args.report_type!r} "
            f"(supported: {', '.join(SUPPORTED_REPORT_TYPES)})",
            file=sys.stderr,
        )
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else None
    try:
        with get_session_factory()() as session:
            row = generate_report(session, args.report_type, output_dir)
            session.commit()
    except Exception as exc:  # noqa: BLE001 - CLI: print and fail closed
        print(f"report generation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    file_path = Path(row.path)
    size = file_path.stat().st_size if file_path.is_file() else 0
    print(f"report: {row.type} written to {file_path} ({size} bytes, id={row.id})")
    print(f"summary: {row.summary}")
    print("--- top lines ---")
    try:
        for line in file_path.read_text(encoding="utf-8").splitlines()[:10]:
            print(line)
    except OSError as exc:
        print(f"(could not read back the report: {exc})", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse tree (subcommands with stable names/flags)."""
    parser = argparse.ArgumentParser(prog="mkc", description=BANNER)
    parser.add_argument("--base-url", default=None, help="override the API base URL (default from settings/env)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_health = sub.add_parser("health", help="GET /healthz")
    p_health.set_defaults(func=cmd_health)

    p_status = sub.add_parser("status", help="GET /api/v1/status")
    p_status.set_defaults(func=cmd_status)

    p_ingest = sub.add_parser("ingest", help="ingest a source into the registry")
    p_ingest.add_argument("path", help="path to a git repo, directory or file")
    p_ingest.add_argument("--source-type", default="git", choices=["git", "markdown", "chatgpt", "commit", "code", "research"])
    p_ingest.set_defaults(func=cmd_ingest)

    p_search = sub.add_parser("search", help="search the knowledge registry")
    p_search.add_argument("query", help="search query")
    p_search.add_argument("--top-k", type=int, default=10)
    p_search.add_argument("--scope", default="knowledge", choices=["knowledge", "documents", "all"])
    p_search.set_defaults(func=cmd_search)

    p_report = sub.add_parser("report", help="generate a registry report")
    p_report.add_argument("report_type", choices=["project-knowledge", "research-gaps", "implementation-plan"])
    p_report.add_argument("--output-dir", default=None, help="output directory (default: <workspace>/reports)")
    p_report.set_defaults(func=cmd_report)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point (``mkc = mkc.cli:main``)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = bootstrap()
    _configure_logging(settings.mkc_log_level)
    if args.base_url:
        _BASE_URL_OVERRIDE[0] = args.base_url
    print(BANNER)
    if not settings.token_is_configured:
        print("warning: MKC_API_TOKEN is not set; authenticated commands will fail closed.", file=sys.stderr)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
