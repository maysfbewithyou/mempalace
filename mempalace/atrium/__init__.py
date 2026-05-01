"""Atrium - the MemPalace UI surface (Track B + Track C of Agent Network build).

PRD: docs/ui/02-mempalace-ui-prd-v0.1.0.md (in-file v0.1.2)
Schema (consumed via REST): Atlas_Agent_Activity_Ledger_Schema_v0.1.2.md

Architecture per PRD §3.1: Atrium extends this Starlette app with Jinja-rendered
routes for browsing the palace and reviewing agent activity. All ledger I/O goes
through Atlas's /api/agent-ledger/* endpoints (no direct DB access).

Versioning: atrium v0.1.0.x in-build sub-versions documented in
Claude Workspace/Claude Projects/Agent Network Ledger/TECHNICAL_CHANGELOG.md.
"""
__version__ = "0.1.0.0"
