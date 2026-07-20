from __future__ import annotations

import re
from typing import Any

_INTERFACES = {
    "webdav": re.compile(r"\bwebdav\b", re.I),
    "s3": re.compile(r"\b(?:s3|s3-compatible)\b", re.I),
    "http": re.compile(r"reverse proxy|listen(?:ing)? (?:on|at)|base url|http port", re.I),
    "https": re.compile(r"reverse proxy|tls termination|https support", re.I),
    "forwarded_headers": re.compile(r"x-forwarded-|forwarded headers?", re.I),
    "oidc": re.compile(r"\b(?:oidc|open id connect|openid connect)\b", re.I),
    "oauth2": re.compile(r"\boauth ?2\b", re.I),
    "postgresql": re.compile(r"\bpostgres(?:ql)?\b", re.I),
}
_NAMED_COMPONENTS = {
    "PhotoSync": re.compile(r"\bphotosync\b", re.I),
    "MinIO": re.compile(r"\bminio\b", re.I),
    "Caddy": re.compile(r"\bcaddy\b", re.I),
    "Traefik": re.compile(r"\btraefik\b", re.I),
    "Nginx": re.compile(r"\bnginx\b", re.I),
}


def extract_compatibility_evidence(
    documents: list[dict[str, Any]],
) -> dict[str, dict[str, list[dict[str, Any]]]]:
    interfaces: dict[str, list[dict[str, Any]]] = {}
    named: dict[str, list[dict[str, Any]]] = {}
    for document in documents:
        content = str(document.get("content", ""))
        source = {
            "path": document.get("path"),
            "url": document.get("url"),
            "commit_sha": document.get("commit_sha"),
        }
        for interface, pattern in _INTERFACES.items():
            match = pattern.search(content)
            if match:
                interfaces.setdefault(interface, []).append(
                    {**source, "quote": match.group(0)}
                )
        for name, pattern in _NAMED_COMPONENTS.items():
            match = pattern.search(content)
            if match:
                named.setdefault(name, []).append(
                    {**source, "quote": match.group(0)}
                )
    return {"interfaces": interfaces, "named_components": named}
