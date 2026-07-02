"""Industry template engine for MyAgentWatch.

Templates are YAML files in templates/ that overlay on top of config.yaml.
Switch templates with one line: `template: "quant_trading"` in config.yaml.
"""

import logging
import os

try:
    import yaml
except ImportError:
    yaml = None

logger = logging.getLogger("myagentwatch.template_engine")

# Priority search paths
TEMPLATE_DIRS = [
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "templates"
    ),
]


def _find_template(name: str) -> str | None:
    for d in TEMPLATE_DIRS:
        p = os.path.join(d, f"{name}.yaml")
        if os.path.exists(p):
            return p
    return None


def list_templates() -> list:
    result = []
    seen = set()
    for d in TEMPLATE_DIRS:
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.endswith(".yaml") and f != "default.yaml":
                name = f[:-5]
                if name not in seen:
                    seen.add(name)
                    result.append({"name": name, "path": os.path.join(d, f)})
    return result


def load_template(name: str) -> dict:
    path = _find_template(name)
    if not path:
        logger.warning(f"Template '{name}' not found in {TEMPLATE_DIRS}")
        return {}

    try:
        if yaml:
            with open(path) as f:
                data = yaml.safe_load(f)
        else:
            import json

            with open(path) as f:
                data = json.load(f)
        logger.info(f"Loaded template '{name}' from {path}")
        return data or {}
    except Exception as e:
        logger.error(f"Error loading template '{name}': {e}")
        return {}


def merge_config(base: dict, template: dict) -> dict:
    """Deep merge template into base. Template values win on conflict.
    Special handling: agent_meta dicts are merged per-key (template augments base)."""
    result = dict(base)

    for key, val in template.items():
        if (
            key == "agent_meta"
            and isinstance(val, dict)
            and isinstance(result.get(key), dict)
        ):
            merged = dict(result[key])
            merged.update(val)
            result[key] = merged
        elif isinstance(val, dict) and isinstance(result.get(key), dict):
            result[key] = {**result[key], **val}
        else:
            result[key] = val

    return result


def apply_template(config: dict) -> dict:
    """Apply the configured template to the base config."""
    template_name = config.get("template", "default")
    if not template_name or template_name == "default":
        return config

    tmpl = load_template(template_name)
    if not tmpl:
        return config

    return merge_config(config, tmpl)
