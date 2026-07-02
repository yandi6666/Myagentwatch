"""Data source registry — the pluggable agent integration hub.

Any external tool can become a MyAgentWatch data source by:

1. Implementing `SourceInterface` (see base.py)
2. Decorating the class with `@register_source("your_type")`
3. Saving the file in this `sources/` directory

See AGENTS_ONBOARD.md for the full guide.
"""

from .base import SourceInterface

SOURCE_REGISTRY: dict[str, type[SourceInterface]] = {}


def register_source(source_type: str):
    """Decorator to register a data source adapter.

    Usage:
        @register_source("n8n_db")
        class N8nDBSource(SourceInterface):
            ...

    After registration, config.yaml can reference it:
        data_sources:
          - name: "n8n"
            type: "n8n_db"
            db_path: "~/.n8n/database.sqlite"
    """

    def decorator(cls: type[SourceInterface]):
        SOURCE_REGISTRY[source_type] = cls
        cls.source_type = source_type
        return cls

    return decorator


def get_registered_sources() -> dict[str, type[SourceInterface]]:
    """Return a copy of the source registry."""
    return SOURCE_REGISTRY.copy()


# Load built-in adapters to trigger registration (side-effect only, register decorators)
from . import (  # noqa: E402
    claude_code,  # noqa: F401
    log_file,  # noqa: F401
    opencode_db,  # noqa: F401
    opencode_log,  # noqa: F401
    sqlite_agent,  # noqa: F401
    system,  # noqa: F401
)
