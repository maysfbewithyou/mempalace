"""
backfill_drawer_extraction_state.py — one-shot manual backfill for v3.0.14+iep.3.

Context
-------
Before the v3.0.14+iep.3 fix, ``KnowledgeGraph.list_source_drawer_ids()`` only
inspected the ``source_file`` column of the ``triples`` table. ``tool_kg_add``
(the MCP tool that callers use during scheduled extraction) only writes
``source_closet``. As a result, every triple filed via ``kg_add`` was
invisible to the bookkeeping, and ``mempalace_list_unextracted_drawers``
returned every drawer in the palace as "unextracted" forever.

The shipped fix changes the query to UNION both columns, so existing
triples filed during the broken window already count their drawers as
extracted — no schema change, no row updates required.

This script is provided as an OPTIONAL data-normalization pass. Run it if
you would rather have a single column that holds the drawer back-link for
every triple (so future tooling that looks at only one column doesn't have
the same blind spot). It copies the ``drawer:<id>`` value from
``source_closet`` into ``source_file`` whenever ``source_file`` is NULL,
and vice versa. It never overwrites an existing non-NULL value and never
touches non-drawer prefixes.

It is a NO-OP for the visible bug (the union query already counts those
drawers) — this is purely belt-and-braces. Do NOT run unless you've read
the diff and want the data normalized.

Usage
-----
    python scripts/backfill_drawer_extraction_state.py            # dry-run, default
    python scripts/backfill_drawer_extraction_state.py --apply    # commit changes
    python scripts/backfill_drawer_extraction_state.py --db /path/to/knowledge_graph.sqlite3 --apply

Default DB path: ~/.mempalace/knowledge_graph.sqlite3
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys

DEFAULT_KG_PATH = os.path.expanduser("~/.mempalace/knowledge_graph.sqlite3")
DRAWER_PREFIX = "drawer:"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--db", default=DEFAULT_KG_PATH, help="Path to knowledge_graph.sqlite3")
    p.add_argument(
        "--apply",
        action="store_true",
        help="Commit changes. Without this flag the script runs as a dry-run.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not os.path.isfile(args.db):
        print(f"ERROR: KG database not found at {args.db}", file=sys.stderr)
        return 2

    print(f"Opening {args.db} (mode={'APPLY' if args.apply else 'dry-run'})")
    conn = sqlite3.connect(args.db, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        # Sanity probe: confirm the table + columns we expect.
        cols = {r[1] for r in conn.execute("PRAGMA table_info(triples)").fetchall()}
        for required in ("source_file", "source_closet"):
            if required not in cols:
                print(
                    f"ERROR: triples table is missing column {required!r}; "
                    f"is this really a MemPalace KG database?",
                    file=sys.stderr,
                )
                return 2

        # 1. closet → file: triples where source_closet is a drawer link
        #    and source_file is NULL.
        closet_to_file_rows = conn.execute(
            f"""
            SELECT id, source_closet
            FROM triples
            WHERE source_closet LIKE '{DRAWER_PREFIX}%'
              AND source_file IS NULL
            """
        ).fetchall()

        # 2. file → closet: triples where source_file is a drawer link
        #    and source_closet is NULL.
        file_to_closet_rows = conn.execute(
            f"""
            SELECT id, source_file
            FROM triples
            WHERE source_file LIKE '{DRAWER_PREFIX}%'
              AND source_closet IS NULL
            """
        ).fetchall()

        print(f"  closet→file candidates: {len(closet_to_file_rows)}")
        print(f"  file→closet candidates: {len(file_to_closet_rows)}")

        if not args.apply:
            print("Dry-run only. Re-run with --apply to commit.")
            return 0

        with conn:
            for row in closet_to_file_rows:
                conn.execute(
                    "UPDATE triples SET source_file = ? WHERE id = ?",
                    (row["source_closet"], row["id"]),
                )
            for row in file_to_closet_rows:
                conn.execute(
                    "UPDATE triples SET source_closet = ? WHERE id = ?",
                    (row["source_file"], row["id"]),
                )

        print(
            f"APPLIED: copied source_closet→source_file for {len(closet_to_file_rows)} row(s); "
            f"copied source_file→source_closet for {len(file_to_closet_rows)} row(s)."
        )
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
