"""
MemPalace configuration system.

Priority: env vars > config file (~/.mempalace/config.json) > defaults
"""

import json
import os
import re
from pathlib import Path


# ── Input validation ──────────────────────────────────────────────────────────
# Two sanitizers, intentionally split:
#
#   sanitize_name   — strict; for filesystem-adjacent fields (wing, room,
#                     agent_name) and controlled-vocabulary fields (predicate).
#                     Blocks /, \, :, and most punctuation.
#
#   sanitize_entity — permissive; for KG subject/object and the `entity`
#                     argument of kg_query / kg_timeline. These are
#                     user-supplied identifiers (file paths, URLs, host:port
#                     endpoints, SHAs, version strings) where the strict
#                     character set silently dropped real fidelity.
#                     Still blocks null bytes, control characters, path
#                     traversal (..), and excessive length.
#
# Why two sanitizers instead of one relaxed one: wing/room values flow into
# filesystem paths and ChromaDB collection metadata where slashes and colons
# are genuinely unsafe. KG subject/object values flow into SQLite text
# columns where they are not interpreted as paths — they're just identifiers.

MAX_NAME_LENGTH = 128
MAX_ENTITY_LENGTH = 256

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_ .'-]{0,126}[a-zA-Z0-9]?$")
# Control characters: 0x00-0x1F (incl. tab/newline/cr) and 0x7F (DEL).
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1F\x7F]")


def sanitize_name(value: str, field_name: str = "name") -> str:
    """Validate and sanitize a wing/room/agent name or KG predicate.

    Strict alphabet — blocks slashes, colons, and most punctuation. Use this
    for any field that flows into a filesystem path, ChromaDB collection
    metadata, or a controlled-vocabulary slot like a predicate.

    For KG subject/object values (which legitimately contain URLs, paths,
    host:port endpoints, etc.), use ``sanitize_entity`` instead.

    Raises ValueError if the name is invalid.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")

    value = value.strip()

    if len(value) > MAX_NAME_LENGTH:
        raise ValueError(f"{field_name} exceeds maximum length of {MAX_NAME_LENGTH} characters")

    # Block path traversal
    if ".." in value or "/" in value or "\\" in value:
        raise ValueError(f"{field_name} contains invalid path characters")

    # Block null bytes
    if "\x00" in value:
        raise ValueError(f"{field_name} contains null bytes")

    # Enforce safe character set
    if not _SAFE_NAME_RE.match(value):
        raise ValueError(f"{field_name} contains invalid characters")

    return value


def sanitize_entity(value: str, field_name: str = "entity") -> str:
    """Validate and sanitize a KG entity value (subject or object).

    Permissive — accepts URLs, file paths, host:port pairs, SHAs, version
    strings, and other real-world identifiers. Slashes, backslashes, and
    colons are all allowed because these values are stored as opaque text
    in SQLite and are not interpreted as filesystem paths.

    Still blocks the things that actually matter:
      - Null bytes (SQL/text safety)
      - Control characters (display/log injection safety)
      - Path traversal sequences (`..`) (defense in depth)
      - Excessive length (DoS / index bloat)

    Use this for the ``subject`` and ``object`` arguments of ``kg_add`` and
    ``kg_invalidate``, and the ``entity`` argument of ``kg_query`` /
    ``kg_timeline``. For wing names, room names, agent names, and KG
    predicates, use ``sanitize_name`` instead.

    Raises ValueError if the value is invalid.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")

    value = value.strip()

    if len(value) > MAX_ENTITY_LENGTH:
        raise ValueError(
            f"{field_name} exceeds maximum length of {MAX_ENTITY_LENGTH} characters"
        )

    # Block path traversal — ".." has no legitimate role in an entity
    # identifier and reliably indicates either an injection attempt or a
    # bug in the caller.
    if ".." in value:
        raise ValueError(f"{field_name} contains '..' which is not allowed")

    # Block null bytes and control characters (covers \x00, tab, newline, CR,
    # and DEL — none of these belong in an identifier).
    if _CONTROL_CHARS_RE.search(value):
        raise ValueError(f"{field_name} contains control characters")

    return value


def sanitize_content(value: str, max_length: int = 100_000) -> str:
    """Validate drawer/diary content length."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("content must be a non-empty string")
    if len(value) > max_length:
        raise ValueError(f"content exceeds maximum length of {max_length} characters")
    if "\x00" in value:
        raise ValueError("content contains null bytes")
    return value


DEFAULT_PALACE_PATH = os.path.expanduser("~/.mempalace/palace")
DEFAULT_COLLECTION_NAME = "mempalace_drawers"

DEFAULT_TOPIC_WINGS = [
    "events",
    "venues",
    "vendors",
    "timelines",
    "budgets",
    "team",
    "clients",
    "productions",
    "equipment",
    "creative",
    "technical",
]

DEFAULT_HALL_KEYWORDS = {
    "events": [
        "event", "gala", "wedding", "corporate", "conference", "exhibition",
        "launch", "reception", "ceremony", "festival", "banquet", "showcase",
    ],
    "venues": [
        "venue", "location", "site", "ballroom", "hall", "outdoor", "stage",
        "capacity", "layout", "floorplan", "setup", "teardown", "load-in",
    ],
    "vendors": [
        "vendor", "caterer", "catering", "florist", "photographer", "dj",
        "band", "rental", "supplier", "contract", "invoice", "quote",
    ],
    "timelines": [
        "timeline", "schedule", "deadline", "milestone", "runsheet", "cue",
        "rehearsal", "load-in", "load-out", "setup", "teardown", "day-of",
    ],
    "budgets": [
        "budget", "cost", "price", "quote", "invoice", "expense", "revenue",
        "margin", "deposit", "payment", "estimate", "line item", "overrun",
    ],
    "team": [
        "team", "crew", "staff", "coordinator", "manager", "director",
        "volunteer", "assign", "role", "shift", "call time", "contact",
    ],
    "clients": [
        "client", "customer", "bride", "groom", "host", "sponsor",
        "preference", "request", "feedback", "approval", "guest list",
    ],
    "productions": [
        "production", "show", "program", "script", "rundown", "cue sheet",
        "lighting", "sound", "av", "video", "projection", "staging",
    ],
    "equipment": [
        "equipment", "gear", "inventory", "rental", "specs", "wattage",
        "dimensions", "rigging", "truss", "cable", "microphone", "speaker",
    ],
    "creative": [
        "design", "theme", "decor", "aesthetic", "color", "mood board",
        "branding", "signage", "centerpiece", "backdrop", "ambiance",
    ],
    "technical": [
        "code", "python", "script", "bug", "error", "api", "database",
        "server", "automation", "integration", "webhook", "deployment",
    ],
}


class MempalaceConfig:
    """Configuration manager for MemPalace.

    Load order: env vars > config file > defaults.
    """

    def __init__(self, config_dir=None):
        """Initialize config.

        Args:
            config_dir: Override config directory (useful for testing).
                        Defaults to ~/.mempalace.
        """
        self._config_dir = (
            Path(config_dir) if config_dir else Path(os.path.expanduser("~/.mempalace"))
        )
        self._config_file = self._config_dir / "config.json"
        self._people_map_file = self._config_dir / "people_map.json"
        self._file_config = {}

        if self._config_file.exists():
            try:
                with open(self._config_file, "r") as f:
                    self._file_config = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._file_config = {}

    @property
    def palace_path(self):
        """Path to the memory palace data directory."""
        env_val = os.environ.get("MEMPALACE_PALACE_PATH") or os.environ.get("MEMPAL_PALACE_PATH")
        if env_val:
            return env_val
        return self._file_config.get("palace_path", DEFAULT_PALACE_PATH)

    @property
    def collection_name(self):
        """ChromaDB collection name."""
        return self._file_config.get("collection_name", DEFAULT_COLLECTION_NAME)

    @property
    def people_map(self):
        """Mapping of name variants to canonical names."""
        if self._people_map_file.exists():
            try:
                with open(self._people_map_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass
        return self._file_config.get("people_map", {})

    @property
    def topic_wings(self):
        """List of topic wing names."""
        return self._file_config.get("topic_wings", DEFAULT_TOPIC_WINGS)

    @property
    def hall_keywords(self):
        """Mapping of hall names to keyword lists."""
        return self._file_config.get("hall_keywords", DEFAULT_HALL_KEYWORDS)

    def init(self):
        """Create config directory and write default config.json if it doesn't exist."""
        self._config_dir.mkdir(parents=True, exist_ok=True)
        # Restrict directory permissions to owner only (Unix)
        try:
            self._config_dir.chmod(0o700)
        except (OSError, NotImplementedError):
            pass  # Windows doesn't support Unix permissions
        if not self._config_file.exists():
            default_config = {
                "palace_path": DEFAULT_PALACE_PATH,
                "collection_name": DEFAULT_COLLECTION_NAME,
                "topic_wings": DEFAULT_TOPIC_WINGS,
                "hall_keywords": DEFAULT_HALL_KEYWORDS,
            }
            with open(self._config_file, "w") as f:
                json.dump(default_config, f, indent=2)
            # Restrict config file to owner read/write only
            try:
                self._config_file.chmod(0o600)
            except (OSError, NotImplementedError):
                pass
        return self._config_file

    def save_people_map(self, people_map):
        """Write people_map.json to config directory.

        Args:
            people_map: Dict mapping name variants to canonical names.
        """
        self._config_dir.mkdir(parents=True, exist_ok=True)
        with open(self._people_map_file, "w") as f:
            json.dump(people_map, f, indent=2)
        return self._people_map_file
