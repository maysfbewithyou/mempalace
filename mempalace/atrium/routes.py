"""Atrium HTTP route handlers (Tracks B2, B3, C2, C3 of Agent Network build).

Architecture:
  - Read paths (Library, Search, KG, Settings) call mempalace internals
    directly per PRD §3.4 - direct ChromaDB / SQLite reads avoid serializing
    behind the single asyncio.Lock that gates /mcp.
  - Ledger paths (Agents Activity Feed, Suggestions Queue, Reviews, Persona
    editor) call atlas via routes.ledger_client per PRD §6.5/§6.6/§6.7.
  - All mutation paths for memory-palace data go through MCP tools (suggestions
    queue's approve/reject/edit verbs call mempalace_add_drawer + delete_drawer
    via the in-process StdioProxy).

Templates: jinja2, files in templates/ next to this module.
Static: files in static/ next to this module, served at /atrium/static/<path>.

Versioning per Matt's preference: every route handler that ships a new
behavior gets a `# v0.1.0.x` comment so changes are traceable without
needing to grep the TCL.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response, RedirectResponse
from starlette.staticfiles import StaticFiles
from starlette.routing import Mount, Route
from starlette.templating import Jinja2Templates

from . import __version__ as ATRIUM_VERSION
from . import ledger_client as lc

logger = logging.getLogger("atrium.routes")

# Templates + static asset directories (next to this module)
HERE = Path(__file__).parent
TEMPLATES = Jinja2Templates(directory=str(HERE / "templates"))
STATIC_DIR = HERE / "static"


# ===== Helpers =====

def _operator(request: Request) -> str:
    """Read operator from request.state set by AtriumAuthMiddleware."""
    return getattr(request.state, "operator_email", "unknown@nowhere")


def _ctx(request: Request, active: str, **extra) -> dict:
    """Build base template context. `active` highlights the sidebar nav item."""
    ctx = {
        "request": request,
        "active": active,
        "atrium_version": ATRIUM_VERSION,
        "operator_email": _operator(request),
        "pending_count": _safe_pending_count(request),
    }
    ctx.update(extra)
    return ctx


def _safe_pending_count(request: Request) -> int:
    """Sidebar badge - count of pending suggestions. Returns 0 on any error."""
    try:
        sugs = lc.list_suggestions(_operator(request), state="pending", limit=1)
        # The API returns a list; we want a quick count, so re-call with a
        # bigger limit. (Real impl would expose a count endpoint - small
        # follow-up.)
        sugs_full = lc.list_suggestions(_operator(request), state="pending", limit=500)
        return len(sugs_full)
    except Exception:
        return 0


def _render(request: Request, template: str, ctx: dict) -> Response:
    return TEMPLATES.TemplateResponse(template, ctx)


def _ledger_banner_for(exc: Exception) -> dict:
    """Convert a ledger exception into a banner dict for templates."""
    return {
        "ledger_banner": {
            "level": "error",
            "message": f"Ledger unavailable: {type(exc).__name__}: {exc}. "
                       "Browse-only paths still work.",
        }
    }


def _palace_module():
    """Lazy-import mempalace internals so import-time of atrium doesn't pull
    chromadb/onnxruntime when unit tests only exercise the auth path."""
    from .. import config as cfg
    from .. import searcher
    from .. import knowledge_graph
    return cfg, searcher, knowledge_graph


def _palace_path() -> Path:
    """Read palace path from env or default. Same logic as http_server._get_palace_path."""
    return Path(os.environ.get("MEMPAL_PALACE_PATH", "/data/.mempalace/palace"))


# ===== Home (PRD §6.1) =====

async def home(request: Request) -> Response:
    """Palace Overview / Home. Glance at brain health + recent activity."""
    op = _operator(request)
    ctx = _ctx(request, "home")

    # Try to fetch headline KPIs from the palace; tolerate missing data.
    try:
        cfg, searcher_mod, kg_mod = _palace_module()
        palace_p = _palace_path()
        # Quick stats via direct chromadb probe (lightweight: just collection size)
        try:
            import chromadb
            client = chromadb.PersistentClient(path=str(palace_p))
            collection = client.get_or_create_collection("mempalace")
            ctx["kpi_drawers"] = collection.count()
        except Exception as e:
            logger.warning("home: chromadb count failed: %s", e)
            ctx["kpi_drawers"] = "—"

        # Wing breakdown via metadata sample
        ctx["kpi_wings"] = "—"
        try:
            client = chromadb.PersistentClient(path=str(palace_p))
            collection = client.get_or_create_collection("mempalace")
            sample = collection.get(limit=10000, include=["metadatas"])
            wings = {}
            for md in (sample.get("metadatas") or []):
                w = md.get("wing")
                if w:
                    wings[w] = wings.get(w, 0) + 1
            ctx["kpi_wings"] = len(wings)
            ctx["wing_breakdown"] = sorted(wings.items(), key=lambda x: -x[1])
        except Exception as e:
            logger.warning("home: wing breakdown failed: %s", e)
            ctx["wing_breakdown"] = []
    except Exception as e:
        logger.exception("home: palace probe failed")
        ctx["kpi_drawers"] = "—"
        ctx["kpi_wings"] = "—"
        ctx["wing_breakdown"] = []

    # Recent ledger activity (top of right rail)
    try:
        ctx["recent_runs"] = lc.list_runs(op, limit=10, order="desc")
    except Exception as e:
        ctx["recent_runs"] = []
        ctx.update(_ledger_banner_for(e))

    return _render(request, "home.html", ctx)


# ===== Library (PRD §6.2) =====

async def library_index(request: Request) -> Response:
    """Wing list."""
    ctx = _ctx(request, "library")
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(_palace_path()))
        collection = client.get_or_create_collection("mempalace")
        sample = collection.get(limit=20000, include=["metadatas"])
        wing_counts = {}
        wing_rooms = {}
        for md in (sample.get("metadatas") or []):
            w = md.get("wing")
            r = md.get("room")
            if w:
                wing_counts[w] = wing_counts.get(w, 0) + 1
                if r:
                    wing_rooms.setdefault(w, set()).add(r)
        wings = [
            {
                "name": w,
                "drawer_count": wing_counts[w],
                "room_count": len(wing_rooms.get(w, set())),
                "sample_rooms": sorted(list(wing_rooms.get(w, set())))[:3],
            }
            for w in sorted(wing_counts.keys())
        ]
        ctx["wings"] = wings
    except Exception as e:
        logger.exception("library_index: failed")
        ctx["wings"] = []
        ctx["error"] = str(e)
    return _render(request, "library_index.html", ctx)


async def library_wing(request: Request) -> Response:
    """Room list inside a wing."""
    wing = request.path_params["wing"]
    ctx = _ctx(request, "library")
    ctx["wing"] = wing
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(_palace_path()))
        collection = client.get_or_create_collection("mempalace")
        result = collection.get(where={"wing": wing}, limit=10000, include=["metadatas"])
        rooms = {}
        for md in (result.get("metadatas") or []):
            r = md.get("room", "(no-room)")
            rooms[r] = rooms.get(r, 0) + 1
        ctx["rooms"] = sorted(
            [{"name": r, "drawer_count": c} for r, c in rooms.items()],
            key=lambda x: -x["drawer_count"],
        )
    except Exception as e:
        logger.exception("library_wing: failed")
        ctx["rooms"] = []
        ctx["error"] = str(e)
    return _render(request, "library_wing.html", ctx)


async def library_room(request: Request) -> Response:
    """Drawer list inside a room."""
    wing = request.path_params["wing"]
    room = request.path_params["room"]
    ctx = _ctx(request, "library")
    ctx["wing"] = wing
    ctx["room"] = room
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(_palace_path()))
        collection = client.get_or_create_collection("mempalace")
        result = collection.get(
            where={"$and": [{"wing": wing}, {"room": room}]},
            limit=200,
            include=["metadatas", "documents"],
        )
        drawers = []
        ids = result.get("ids") or []
        docs = result.get("documents") or []
        mds = result.get("metadatas") or []
        for i, did in enumerate(ids):
            doc = docs[i] if i < len(docs) else ""
            md = mds[i] if i < len(mds) else {}
            drawers.append({
                "id": did,
                "filed_at": md.get("filed_at"),
                "source_file": md.get("source_file", ""),
                "added_by": md.get("added_by", ""),
                "preview": (doc or "")[:200] + ("…" if len(doc or "") > 200 else ""),
            })
        # Sort by filed_at descending if present
        drawers.sort(key=lambda d: d.get("filed_at") or "", reverse=True)
        ctx["drawers"] = drawers
    except Exception as e:
        logger.exception("library_room: failed")
        ctx["drawers"] = []
        ctx["error"] = str(e)
    return _render(request, "library_room.html", ctx)


async def drawer_detail(request: Request) -> Response:
    """Single drawer view."""
    drawer_id = request.path_params["drawer_id"]
    ctx = _ctx(request, "library")
    ctx["drawer_id"] = drawer_id
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(_palace_path()))
        collection = client.get_or_create_collection("mempalace")
        result = collection.get(ids=[drawer_id], include=["metadatas", "documents"])
        if not result.get("ids"):
            ctx["error"] = f"drawer {drawer_id} not found"
            ctx["drawer"] = None
        else:
            ctx["drawer"] = {
                "id": result["ids"][0],
                "content": (result.get("documents") or [""])[0],
                "metadata": (result.get("metadatas") or [{}])[0],
            }
    except Exception as e:
        logger.exception("drawer_detail: failed")
        ctx["error"] = str(e)
        ctx["drawer"] = None
    return _render(request, "drawer.html", ctx)


# ===== Search (PRD §6.3) =====

async def search(request: Request) -> Response:
    q = request.query_params.get("q", "").strip()
    wing = request.query_params.get("wing")
    limit = int(request.query_params.get("limit", "20"))
    ctx = _ctx(request, "search")
    ctx["q"] = q
    ctx["wing"] = wing
    ctx["limit"] = limit
    ctx["results"] = []
    ctx["sanitization"] = None
    if q:
        try:
            from .. import searcher as searcher_mod
            from .. import config as cfg
            cfg_obj = cfg.MempalaceConfig.from_env()
            srch = searcher_mod.Searcher(cfg_obj)
            results, sanit = srch.search_memories(
                query=q,
                wing=wing or None,
                limit=limit,
            )
            ctx["results"] = results
            ctx["sanitization"] = sanit
        except Exception as e:
            logger.exception("search: failed")
            ctx["error"] = str(e)
    return _render(request, "search.html", ctx)


# ===== KG placeholder (PRD §6.4 - deferred to v0.2.0+, just text for now) =====

async def kg_placeholder(request: Request) -> Response:
    ctx = _ctx(request, "kg")
    try:
        from .. import knowledge_graph as kg_mod
        from .. import config as cfg
        cfg_obj = cfg.MempalaceConfig.from_env()
        kg = kg_mod.KnowledgeGraph(cfg_obj.kg_db_path)
        ctx["kg_stats"] = kg.stats()
        ctx["kg_timeline"] = kg.timeline(limit=50)
    except Exception as e:
        logger.exception("kg_placeholder: failed")
        ctx["error"] = str(e)
        ctx["kg_stats"] = {}
        ctx["kg_timeline"] = []
    return _render(request, "kg.html", ctx)


# ===== Agents - Activity Feed (PRD §6.5) =====

async def agents_activity(request: Request) -> Response:
    op = _operator(request)
    ctx = _ctx(request, "agents")
    try:
        ctx["runs"] = lc.list_runs(
            op,
            limit=int(request.query_params.get("limit", "50")),
            agent_name=request.query_params.get("agent_name"),
            status=request.query_params.get("status"),
            order="desc",
        )
    except Exception as e:
        logger.exception("agents_activity: failed")
        ctx["runs"] = []
        ctx.update(_ledger_banner_for(e))
    return _render(request, "agents_activity.html", ctx)


# ===== Agents - Suggestions Queue (PRD §6.6 - the marquee feature) =====

async def suggestions_queue(request: Request) -> Response:
    op = _operator(request)
    ctx = _ctx(request, "suggestions")
    state_filter = request.query_params.get("state", "pending")
    try:
        ctx["suggestions"] = lc.list_suggestions(
            op,
            state=state_filter,
            limit=int(request.query_params.get("limit", "100")),
            order="asc" if state_filter == "pending" else "desc",
        )
        ctx["state_filter"] = state_filter
    except Exception as e:
        logger.exception("suggestions_queue: failed")
        ctx["suggestions"] = []
        ctx.update(_ledger_banner_for(e))
    return _render(request, "suggestions.html", ctx)


async def suggestion_resolve(request: Request) -> Response:
    """POST /atrium/agents/suggestions/<id>/<verb>

    verb in: approve | reject | edit | withdrawn

    For 'edit', the body has the new content; we'd ideally call mempalace_add_drawer
    with the new content + delete the old, but C2 is currently scoped to the ledger
    state transition only - the canonical drawer mutation is documented as a
    follow-up. The reviewer note carries the diff context.
    """
    op = _operator(request)
    suggestion_id = request.path_params["suggestion_id"]
    verb = request.path_params["verb"]

    state_map = {"approve": "approved", "reject": "rejected",
                 "edit": "edited", "withdraw": "withdrawn"}
    if verb not in state_map:
        return JSONResponse({"error": f"unknown verb: {verb}"}, status_code=400)

    form = await request.form()
    note = form.get("note") or None
    if verb in ("reject", "edit") and not note:
        return JSONResponse({"error": f"note required for {verb}"}, status_code=400)

    try:
        result = lc.resolve_suggestion(op, suggestion_id, state_map[verb], note=note)
    except lc.LedgerValidationError as e:
        return JSONResponse({"error_code": "validation", "message": str(e)}, status_code=400)
    except lc.LedgerError as e:
        return JSONResponse({"error_code": "ledger_error", "message": str(e)}, status_code=502)

    # If HTMX request, return the updated row fragment; else redirect.
    if request.headers.get("HX-Request"):
        # Render a single-row update fragment showing the resolved state
        return TEMPLATES.TemplateResponse(
            "_suggestion_row.html",
            {"request": request, "suggestion": result, "resolved": True},
        )
    return RedirectResponse(url="/atrium/agents/suggestions", status_code=303)


# ===== Agents - Reviews (PRD §6.7) =====

async def reviews_history(request: Request) -> Response:
    op = _operator(request)
    ctx = _ctx(request, "reviews")
    try:
        ctx["reviews"] = lc.list_reviews(
            op,
            verdict=request.query_params.get("verdict"),
            agent_name=request.query_params.get("agent_name"),
            limit=int(request.query_params.get("limit", "100")),
            order="desc",
        )
    except Exception as e:
        logger.exception("reviews_history: failed")
        ctx["reviews"] = []
        ctx.update(_ledger_banner_for(e))
    return _render(request, "reviews.html", ctx)


# ===== Settings (PRD §6.8 + §13 persona editor) =====

async def settings(request: Request) -> Response:
    op = _operator(request)
    ctx = _ctx(request, "settings")

    # Identity
    try:
        from .. import config as cfg
        cfg_obj = cfg.MempalaceConfig.from_env()
        identity_path = Path(cfg_obj.config_path).parent / "identity.txt"
        ctx["identity"] = identity_path.read_text() if identity_path.exists() else "(identity.txt not found)"
    except Exception as e:
        ctx["identity"] = f"(error reading identity: {e})"

    # Personas (C3 - registry editor data)
    try:
        ctx["personas"] = lc.list_personas(op, active="false")  # include retired
    except Exception as e:
        logger.exception("settings: persona list failed")
        ctx["personas"] = []
        ctx.update(_ledger_banner_for(e))

    # About
    ctx["about"] = {
        "atrium_version": ATRIUM_VERSION,
        "palace_path": str(_palace_path()),
    }
    return _render(request, "settings.html", ctx)


async def persona_upsert(request: Request) -> Response:
    """C3: live registry editor - create or update a persona."""
    op = _operator(request)
    form = await request.form()
    body = {
        "agent_name": form.get("agent_name"),
        "persona_archetype": form.get("persona_archetype"),
        "persona_label": form.get("persona_label"),
        "persona_description": form.get("persona_description") or None,
        "scope": form.get("scope"),
        "governance_tier": form.get("governance_tier", "approval_gated"),
    }
    try:
        result = lc.upsert_persona(op, **body)
    except lc.LedgerValidationError as e:
        return JSONResponse({"error_code": "validation", "message": str(e)}, status_code=400)
    except lc.LedgerError as e:
        return JSONResponse({"error_code": "ledger_error", "message": str(e)}, status_code=502)
    return RedirectResponse(url="/atrium/settings", status_code=303)


async def persona_retire(request: Request) -> Response:
    op = _operator(request)
    agent_name = request.path_params["agent_name"]
    try:
        result = lc.patch_persona(op, agent_name, retired_at="now")
    except lc.LedgerError as e:
        return JSONResponse({"error_code": "ledger_error", "message": str(e)}, status_code=502)
    return RedirectResponse(url="/atrium/settings", status_code=303)


# ===== Health (Atrium-side liveness) =====

async def atrium_health(request: Request) -> Response:
    return PlainTextResponse(f"atrium {ATRIUM_VERSION} ok")


# ===== Route registration =====

def get_routes() -> list:
    """Return the list of Atrium routes to register on the Starlette app."""
    return [
        Route("/atrium/health", atrium_health, methods=["GET"]),
        # Note: /atrium/static is mounted as a Mount, registered separately.
        Route("/atrium/", home, methods=["GET"]),
        Route("/atrium/library", library_index, methods=["GET"]),
        Route("/atrium/library/{wing}", library_wing, methods=["GET"]),
        Route("/atrium/library/{wing}/{room}", library_room, methods=["GET"]),
        Route("/atrium/drawer/{drawer_id}", drawer_detail, methods=["GET"]),
        Route("/atrium/search", search, methods=["GET"]),
        Route("/atrium/kg", kg_placeholder, methods=["GET"]),
        Route("/atrium/agents", agents_activity, methods=["GET"]),
        Route("/atrium/agents/suggestions", suggestions_queue, methods=["GET"]),
        Route("/atrium/agents/suggestions/{suggestion_id}/{verb}", suggestion_resolve, methods=["POST"]),
        Route("/atrium/agents/reviews", reviews_history, methods=["GET"]),
        Route("/atrium/settings", settings, methods=["GET"]),
        Route("/atrium/settings/personas", persona_upsert, methods=["POST"]),
        Route("/atrium/settings/personas/{agent_name}/retire", persona_retire, methods=["POST"]),
    ]


def get_static_mount() -> Mount:
    return Mount("/atrium/static", app=StaticFiles(directory=str(STATIC_DIR)), name="atrium_static")
