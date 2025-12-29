# File Version: 0.1.3
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from jinja2 import Environment, FileSystemLoader, select_autoescape


def _identity_translate(value: str, *args: Any, **kwargs: Any) -> str:
    """Stub translation function that returns the input unchanged."""
    return value


def build_environment(template_path: Path) -> Environment:
    loader = FileSystemLoader(str(template_path))
    env = Environment(  # noqa: S701 (we want full control)
        loader=loader,
        autoescape=select_autoescape(["html", "xml", "j2"]),
        enable_async=False,
        trim_blocks=True,
        lstrip_blocks=True,
        extensions=["jinja2.ext.do"],
    )
    env.globals["_"] = _identity_translate
    return env


def render(env: Environment, template_name: str, context: Dict[str, Any]) -> str:
    template = env.get_template(template_name)
    # Ensure _ is always available even if context tries to override it with None
    if "_" not in context or context.get("_") is None:
        context["_"] = _identity_translate
    return template.render(**context)
