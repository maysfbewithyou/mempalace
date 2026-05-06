"""
verify_drawer_bookkeeping_fix.py — standalone verifier for v3.0.14+iep.3.

Reproduces the test cases in tests/test_knowledge_graph.py::TestDrawerSourceBookkeeping
without needing pytest or chromadb installed. Use this on machines where the
full test suite cannot be set up (e.g., Windows boxes without MSVC build
tools where chroma-hnswlib won't compile).

Run:  python scripts/verify_drawer_bookkeeping_fix.py

Exits 0 on success, 1 on any failure.
"""

from __future__ import annotations

import os
import sys
import tempfile

# Ensure the repo root is importable when run as a script.
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from mempalace.knowledge_graph import KnowledgeGraph  # noqa: E402


def _fresh_kg() -> KnowledgeGraph:
    fd, path = tempfile.mkstemp(prefix="kg_verify_", suffix=".sqlite3")
    os.close(fd)
    os.unlink(path)  # KG creates it itself; just want a unique path.
    return KnowledgeGraph(db_path=path)


def _check(label: str, cond: bool):
    marker = "PASS" if cond else "FAIL"
    print(f"  [{marker}] {label}")
    if not cond:
        _check.failed += 1


_check.failed = 0


def main() -> int:
    print("verify_drawer_bookkeeping_fix.py — exercising list_source_drawer_ids")

    print("case 1: source_file path (auto-extract / backfill)")
    kg = _fresh_kg()
    kg.add_triple(
        "Alice", "knows", "Bob", source_file="drawer:drawer_wing_a_room_x_aaaa1111"
    )
    ids = kg.list_source_drawer_ids()
    _check("source_file drawer id present", "drawer_wing_a_room_x_aaaa1111" in ids)

    print("case 2: source_closet path (the kg_add MCP path — was broken)")
    kg = _fresh_kg()
    kg.add_triple(
        "Alice", "knows", "Bob", source_closet="drawer:drawer_wing_b_room_y_bbbb2222"
    )
    ids = kg.list_source_drawer_ids()
    _check("source_closet drawer id present", "drawer_wing_b_room_y_bbbb2222" in ids)

    print("case 3: both columns unioned")
    kg = _fresh_kg()
    kg.add_triple("A", "knows", "B", source_file="drawer:from_file_path_cccc3333")
    kg.add_triple("C", "knows", "D", source_closet="drawer:from_closet_path_dddd4444")
    ids = kg.list_source_drawer_ids()
    _check("from_file_path_cccc3333 present", "from_file_path_cccc3333" in ids)
    _check("from_closet_path_dddd4444 present", "from_closet_path_dddd4444" in ids)
    _check("only the two drawer ids", ids == {"from_file_path_cccc3333", "from_closet_path_dddd4444"})

    print("case 4: non-drawer prefixes ignored")
    kg = _fresh_kg()
    kg.add_triple("E", "knows", "F", source_closet="closet:not_a_drawer")
    kg.add_triple("G", "knows", "H", source_file="file:/some/path.md")
    ids = kg.list_source_drawer_ids()
    _check("non-drawer sources excluded", ids == set())

    print("case 5: NULL source columns are safe and excluded")
    kg = _fresh_kg()
    kg.add_triple("I", "knows", "J")
    ids = kg.list_source_drawer_ids()
    _check("NULL source columns excluded", ids == set())

    if _check.failed:
        print(f"\n{_check.failed} check(s) FAILED")
        return 1
    print("\nAll checks PASSED — column-union bookkeeping is wired correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
