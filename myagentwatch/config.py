"""Configuration loader for MyAgentWatch."""

import logging
import os

import yaml

from myagentwatch.templates.template_engine import apply_template

logger = logging.getLogger("myagentwatch.config")

DEFAULT_CONFIG = {
    "version": 1,
    "data_sources": [
        {
            "name": "main-opencode",
            "type": "opencode_db",
            "db_path": "~/.local/share/opencode/opencode.db",
            "log_dir": "~/.local/share/opencode/log",
            "enabled": True,
        }
    ],
    "agent_meta": {},
    "alert_rules": [],
    "poll_interval": 2,
    "write_interval": 15,
    "agent_stale_timeout": 300,
    "log_archive_days": 7,
    "log_retention_days": 365,
}


def _expand_path(path: str) -> str:
    if path and path.startswith("~"):
        return os.path.expanduser(path)
    return path


def load_config(config_path: str = None) -> dict:
    """Load configuration from YAML file, merging with defaults and template."""
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "config.yaml"
        )

    config = dict(DEFAULT_CONFIG)

    if os.path.exists(config_path):
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}
        _deep_merge(config, user_config)

    # Apply industry template if configured
    template_name = config.get("template", "")
    if template_name and template_name != "default":
        config = apply_template(config)
        logger.info(f"Applied template: {template_name}")

    # Expand paths in data sources
    for ds in config.get("data_sources", []):
        ds["db_path"] = _expand_path(ds.get("db_path", ""))
        ds["log_dir"] = _expand_path(ds.get("log_dir", ""))

    return config


def _deep_merge(base: dict, override: dict):
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        elif (
            key in base
            and isinstance(base[key], list)
            and isinstance(value, list)
            and base[key]
            and isinstance(base[key][0], dict)
            and "name" in base[key][0]
        ):
            # Merge lists of named dicts (e.g. alert_rules):
            # template augments, same-name overrides, non-conflicting items preserved
            merged = {
                item["name"]: dict(item)
                for item in base[key]
                if isinstance(item, dict) and "name" in item
            }
            for item in value:
                if not isinstance(item, dict):
                    continue
                item_name = item.get("name")
                if item_name and item_name in merged:
                    merged[item_name].update(item)
                elif item_name:
                    merged[item_name] = dict(item)
            base[key] = list(merged.values())
        else:
            base[key] = value
