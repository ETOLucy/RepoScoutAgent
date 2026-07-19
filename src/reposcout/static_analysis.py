from __future__ import annotations

import json
import re
import tomllib
from pathlib import PurePosixPath
from typing import Any


def _dependency_names(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [str(key) for key in value]
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, str)]
    return []


def manifest_signals(path: str, content: str) -> list[str]:
    """Extract dependency names without executing or importing repository code."""
    name = PurePosixPath(path).name.casefold()
    dependencies: list[str] = []
    try:
        if name == "package.json":
            payload = json.loads(content)
            if isinstance(payload, dict):
                for key in ("dependencies", "devDependencies", "peerDependencies"):
                    dependencies.extend(_dependency_names(payload.get(key)))
        elif name in {"pyproject.toml", "cargo.toml"}:
            payload = tomllib.loads(content)
            if name == "pyproject.toml":
                project = payload.get("project", {})
                poetry = payload.get("tool", {}).get("poetry", {})
                dependencies.extend(_dependency_names(project.get("dependencies")))
                dependencies.extend(_dependency_names(poetry.get("dependencies")))
            else:
                dependencies.extend(_dependency_names(payload.get("dependencies")))
        elif name == "go.mod":
            dependencies.extend(
                match.group(1)
                for match in re.finditer(
                    r"^\s*(?:require\s+)?([a-z0-9_.-]+(?:/[a-z0-9_.-]+)+)\s+v\d",
                    content,
                    re.I | re.M,
                )
            )
        elif name.startswith("requirements") and name.endswith(".txt"):
            dependencies.extend(
                match.group(1)
                for line in content.splitlines()
                if (match := re.match(r"\s*([a-z0-9_.-]+)", line, re.I))
                and not line.lstrip().startswith(("#", "-"))
            )
    except (json.JSONDecodeError, tomllib.TOMLDecodeError, TypeError):
        return []
    return list(dict.fromkeys(item.casefold() for item in dependencies))[:100]
