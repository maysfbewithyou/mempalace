"""
test_knowledge_graph.py — Tests for the temporal knowledge graph.

Covers: entity CRUD, triple CRUD, temporal queries, invalidation,
timeline, stats, and edge cases (duplicate triples, ID collisions).
"""


class TestEntityOperations:
    def test_add_entity(self, kg):
        eid = kg.add_entity("Alice", entity_type="person")
        assert eid == "alice"

    def test_add_entity_normalizes_id(self, kg):
        eid = kg.add_entity("Dr. Chen", entity_type="person")
        assert eid == "dr._chen"

    def test_add_entity_upsert(self, kg):
        kg.add_entity("Alice", entity_type="person")
        kg.add_entity("Alice", entity_type="engineer")
        # Should not raise — INSERT OR REPLACE
        stats = kg.stats()
        assert stats["entities"] == 1


class TestTripleOperations:
    def test_add_triple_creates_entities(self, kg):
        tid = kg.add_triple("Alice", "knows", "Bob")
        assert tid.startswith("t_alice_knows_bob_")
        stats = kg.stats()
        assert stats["entities"] == 2  # auto-created

    def test_add_triple_with_dates(self, kg):
        tid = kg.add_triple("Max", "does", "swimming", valid_from="2025-01-01")
        assert tid.startswith("t_max_does_swimming_")

    def test_duplicate_triple_returns_existing_id(self, kg):
        tid1 = kg.add_triple("Alice", "knows", "Bob")
        tid2 = kg.add_triple("Alice", "knows", "Bob")
        assert tid1 == tid2

    def test_invalidated_triple_allows_re_add(self, kg):
        tid1 = kg.add_triple("Alice", "works_at", "Acme")
        kg.invalidate("Alice", "works_at", "Acme", ended="2025-01-01")
        tid2 = kg.add_triple("Alice", "works_at", "Acme")
        assert tid1 != tid2  # new triple since old one was closed


class TestQueries:
    def test_query_outgoing(self, seeded_kg):
        results = seeded_kg.query_entity("Alice", direction="outgoing")
        predicates = {r["predicate"] for r in results}
        assert "parent_of" in predicates
        assert "works_at" in predicates

    def test_query_incoming(self, seeded_kg):
        results = seeded_kg.query_entity("Max", direction="incoming")
        assert any(r["subject"] == "Alice" and r["predicate"] == "parent_of" for r in results)

    def test_query_both_directions(self, seeded_kg):
        results = seeded_kg.query_entity("Max", direction="both")
        directions = {r["direction"] for r in results}
        assert "outgoing" in directions
        assert "incoming" in directions

    def test_query_as_of_filters_expired(self, seeded_kg):
        results = seeded_kg.query_entity("Alice", as_of="2023-06-01", direction="outgoing")
        employers = [r["object"] for r in results if r["predicate"] == "works_at"]
        assert "Acme Corp" in employers
        assert "NewCo" not in employers

    def test_query_as_of_shows_current(self, seeded_kg):
        results = seeded_kg.query_entity("Alice", as_of="2025-06-01", direction="outgoing")
        employers = [r["object"] for r in results if r["predicate"] == "works_at"]
        assert "NewCo" in employers
        assert "Acme Corp" not in employers

    def test_query_relationship(self, seeded_kg):
        results = seeded_kg.query_relationship("does")
        assert len(results) == 2  # swimming + chess


class TestInvalidation:
    def test_invalidate_sets_valid_to(self, seeded_kg):
        seeded_kg.invalidate("Max", "does", "chess", ended="2026-01-01")
        results = seeded_kg.query_entity("Max", direction="outgoing")
        chess = [r for r in results if r["object"] == "chess"]
        assert len(chess) == 1
        assert chess[0]["valid_to"] == "2026-01-01"
        assert chess[0]["current"] is False


class TestTimeline:
    def test_timeline_all(self, seeded_kg):
        tl = seeded_kg.timeline()
        assert len(tl) >= 4

    def test_timeline_entity(self, seeded_kg):
        tl = seeded_kg.timeline("Max")
        subjects_and_objects = {t["subject"] for t in tl} | {t["object"] for t in tl}
        assert "Max" in subjects_and_objects

    def test_timeline_global_has_limit(self, kg):
        # Add > 100 triples
        for i in range(105):
            kg.add_triple(f"entity_{i}", "relates_to", f"entity_{i + 1}")
        tl = kg.timeline()
        assert len(tl) == 100  # LIMIT 100

    def test_timeline_entity_has_limit(self, kg):
        # Add > 100 triples all connected to a single entity
        for i in range(105):
            kg.add_triple(
                "hub", "connects_to", f"spoke_{i}", valid_from=f"2025-01-{(i % 28) + 1:02d}"
            )
        tl = kg.timeline("hub")
        assert len(tl) == 100  # LIMIT 100 on entity-filtered branch


class TestWALMode:
    def test_wal_mode_enabled(self, kg):
        conn = kg._conn()
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        assert mode == "wal"


class TestStats:
    def test_stats_empty(self, kg):
        stats = kg.stats()
        assert stats["entities"] == 0
        assert stats["triples"] == 0

    def test_stats_seeded(self, seeded_kg):
        stats = seeded_kg.stats()
        assert stats["entities"] >= 4
        assert stats["triples"] == 5
        assert stats["current_facts"] == 4  # 1 expired (Acme Corp)
        assert stats["expired_facts"] == 1


class TestDrawerSourceBookkeeping:
    """Regression tests for v3.0.14+iep.3:
    list_source_drawer_ids must inspect BOTH source_file and source_closet
    so triples filed via tool_kg_add (which writes source_closet) count
    the underlying drawer as extracted in tool_list_unextracted_drawers.
    """

    def test_source_file_path_bookkeeps(self, kg):
        # Path A: triples written with source_file (auto-extract / backfill)
        kg.add_triple(
            "Alice", "knows", "Bob", source_file="drawer:drawer_wing_a_room_x_aaaa1111"
        )
        ids = kg.list_source_drawer_ids()
        assert "drawer_wing_a_room_x_aaaa1111" in ids

    def test_source_closet_path_bookkeeps(self, kg):
        # Path B: triples written with source_closet (the kg_add MCP tool path
        # — this was the broken case before v3.0.14+iep.3).
        kg.add_triple(
            "Alice", "knows", "Bob", source_closet="drawer:drawer_wing_b_room_y_bbbb2222"
        )
        ids = kg.list_source_drawer_ids()
        assert "drawer_wing_b_room_y_bbbb2222" in ids

    def test_both_columns_unioned(self, kg):
        kg.add_triple(
            "A", "knows", "B", source_file="drawer:from_file_path_cccc3333"
        )
        kg.add_triple(
            "C", "knows", "D", source_closet="drawer:from_closet_path_dddd4444"
        )
        ids = kg.list_source_drawer_ids()
        assert "from_file_path_cccc3333" in ids
        assert "from_closet_path_dddd4444" in ids

    def test_non_drawer_prefixes_ignored(self, kg):
        kg.add_triple("E", "knows", "F", source_closet="closet:not_a_drawer")
        kg.add_triple("G", "knows", "H", source_file="file:/some/path.md")
        ids = kg.list_source_drawer_ids()
        assert ids == set()

    def test_null_source_columns_safe(self, kg):
        # Triples with both columns NULL must not raise and must not show up.
        kg.add_triple("I", "knows", "J")
        ids = kg.list_source_drawer_ids()
        assert ids == set()
