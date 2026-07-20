from __future__ import annotations

import re

from .search.models import ComponentRole, SearchIntent

_ROLE_RULES = (
    (
        "mobile_sync",
        re.compile(r"mobile|android|ios|phone|手机|相册.*备份|自动备份", re.I),
        ["PhotoSync WebDAV", "mobile photo backup WebDAV"],
        ["webdav", "s3"],
    ),
    (
        "object_storage",
        re.compile(r"object storage|s3|对象存储|海量存储", re.I),
        ["S3 compatible object storage", "MinIO"],
        ["s3"],
    ),
    (
        "reverse_proxy",
        re.compile(r"reverse proxy|https|tls|domain|反向代理|域名|证书", re.I),
        ["reverse proxy Docker", "Caddy Traefik Nginx"],
        ["http", "https", "forwarded_headers"],
    ),
)


def infer_component_roles(intent: SearchIntent) -> list[ComponentRole]:
    text_by_requirement = {
        item.id: " ".join(
            [item.description, *item.retrieval_terms, *item.evidence_sources]
        )
        for item in intent.requirements
    }
    roles = []
    for role, pattern, search_terms, interfaces in _ROLE_RULES:
        fulfills = [
            requirement_id
            for requirement_id, text in text_by_requirement.items()
            if pattern.search(text)
        ]
        if fulfills:
            roles.append(
                ComponentRole(
                    role=role,
                    purpose=f"Provide the {role.replace('_', ' ')} capability",
                    search_terms=search_terms,
                    compatibility_interfaces=interfaces,
                    fulfills=fulfills,
                )
            )
    return roles
