from __future__ import annotations

import re
from typing import Any

from .search.models import SearchIntent


def _display_name(full_name: str) -> str:
    return full_name.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ").title()


def _requirement_descriptions(intent: SearchIntent) -> dict[str, str]:
    return {item.id: item.description for item in intent.requirements}


def _evidence_confidence(criteria: list[dict[str, Any]]) -> str:
    if criteria and all(
        item.get("status") == "satisfied"
        and item.get("implementation_status") == "implemented"
        for item in criteria
    ):
        return "implementation_verified"
    if criteria and all(item.get("status") == "satisfied" for item in criteria):
        return "documentation_verified"
    return "partial"


def _deployment_status(
    criteria: list[dict[str, Any]], descriptions: dict[str, str]
) -> str:
    deployment_words = re.compile(r"docker|compose|container|deploy|部署|容器", re.I)
    deployment = [
        item
        for item in criteria
        if deployment_words.search(descriptions.get(str(item.get("requirement_id")), ""))
    ]
    if not deployment:
        return "not_requested"
    if any(item.get("status") == "violated" for item in deployment):
        return "blocked"
    if all(item.get("status") == "satisfied" for item in deployment):
        return "documented"
    return "needs_validation"


_NAMED_ROLES = {
    "PhotoSync": "mobile_sync",
    "MinIO": "object_storage",
    "Caddy": "reverse_proxy",
    "Traefik": "reverse_proxy",
    "Nginx": "reverse_proxy",
}


def _interfaces(item: dict[str, Any]) -> set[str]:
    return set(item.get("compatibility", {}).get("interfaces", {}))


def _component_for_role(
    role: Any,
    primary: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    expected = set(role.compatibility_interfaces)
    primary_interfaces = _interfaces(primary)
    compatible: list[tuple[dict[str, Any], list[str]]] = []
    for candidate in candidates:
        if role.role not in candidate.get("component_roles", []):
            continue
        shared = primary_interfaces & _interfaces(candidate)
        if expected:
            shared &= expected
        if shared:
            compatible.append((candidate, sorted(shared)))
    if not compatible:
        return None
    compatible.sort(key=lambda item: float(item[0].get("score", 0)), reverse=True)
    candidate, shared_interfaces = compatible[0]
    return {
        "role": role.role,
        "name": candidate.get("full_name"),
        "url": candidate.get("url"),
        "reason": candidate.get("summary") or candidate.get("description"),
        "compatibility_status": "interface_verified",
        "shared_interfaces": shared_interfaces,
        "compatibility_evidence": {
            "primary": {
                interface: primary["compatibility"]["interfaces"][interface]
                for interface in shared_interfaces
            },
            "component": {
                interface: candidate["compatibility"]["interfaces"][interface]
                for interface in shared_interfaces
            },
        },
    }


def _documented_components(primary: dict[str, Any]) -> list[dict[str, Any]]:
    named = primary.get("compatibility", {}).get("named_components", {})
    return [
        {
            "role": _NAMED_ROLES[name],
            "name": name,
            "url": evidence[0].get("url") if evidence else None,
            "reason": f"主组件文档明确提及 {name}",
            "compatibility_status": "documented_by_primary",
            "shared_interfaces": [],
            "compatibility_evidence": {"primary": evidence, "component": []},
        }
        for name, evidence in named.items()
        if name in _NAMED_ROLES
    ]


def build_solutions(
    intent: SearchIntent,
    recommendations: list[dict[str, Any]],
    component_candidates: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Turn evidence-checked repositories into actionable solution proposals."""
    descriptions = _requirement_descriptions(intent)
    solutions: list[dict[str, Any]] = []
    all_components = component_candidates or recommendations
    role_by_name = {item.role: item for item in intent.component_roles}
    for rank, recommendation in enumerate(recommendations, start=1):
        criteria = list(recommendation.get("criteria", []))
        satisfied = [
            descriptions.get(str(item.get("requirement_id")), str(item.get("requirement_id")))
            for item in criteria
            if item.get("status") == "satisfied"
        ]
        gaps = [
            {
                "requirement_id": item.get("requirement_id"),
                "description": descriptions.get(
                    str(item.get("requirement_id")), str(item.get("requirement_id"))
                ),
                "status": item.get("status"),
                "action": (
                    "需要替代组件或调整此项要求"
                    if item.get("status") == "violated"
                    else "上线前继续查证或完成小规模验证"
                ),
            }
            for item in criteria
            if item.get("status") in {"unknown", "violated"}
        ]
        full_name = str(recommendation.get("full_name", ""))
        near_miss = recommendation.get("match_kind") == "near_miss"
        components: list[dict[str, Any]] = [
            {
                "role": "primary",
                "name": full_name,
                "url": recommendation.get("url"),
                "reason": recommendation.get("summary")
                or recommendation.get("description"),
                "compatibility_status": "primary",
                "shared_interfaces": sorted(_interfaces(recommendation)),
                "compatibility_evidence": {},
            }
        ]
        selected_roles: set[str] = set()
        for role in intent.component_roles:
            component = _component_for_role(role, recommendation, all_components)
            if component:
                components.append(component)
                selected_roles.add(role.role)
        for component in _documented_components(recommendation):
            if component["role"] not in selected_roles:
                components.append(component)
                selected_roles.add(component["role"])
        for gap in gaps:
            matching_roles = [
                role_by_name[role_name]
                for role_name in selected_roles
                if role_name in role_by_name
                and gap["requirement_id"] in role_by_name[role_name].fulfills
            ]
            if matching_roles:
                gap["action"] = "已有兼容配套组件候选，组合上线前执行端到端验证"
        positioning = (
            "没有候选满足全部硬条件时保留的最接近方案"
            if near_miss
            else f"覆盖 {len(satisfied)}/{max(1, len(criteria))} 项已验证需求的主方案"
        )
        rollout_steps = [
            f"按 {full_name} 的官方文档完成隔离环境部署",
            "使用当前证据清单逐项执行验收",
        ]
        if gaps:
            rollout_steps.append("先补齐或验证缺口，再迁移正式数据")
        else:
            rollout_steps.append("小规模导入数据验证后再进入正式环境")
        solutions.append(
            {
                "id": f"solution-{rank}",
                "title": (
                    f"条件取舍方案：{_display_name(full_name)}"
                    if near_miss
                    else f"推荐方案：{_display_name(full_name)}"
                ),
                "positioning": positioning,
                "score": recommendation.get("score", 0),
                "match_kind": recommendation.get("match_kind", "eligible"),
                "components": components,
                "verified_capabilities": satisfied,
                "gaps": gaps,
                "rollout_steps": rollout_steps,
                "evidence_confidence": _evidence_confidence(criteria),
                "deployment_status": _deployment_status(criteria, descriptions),
                "source_repository": full_name,
                "source_repositories": [
                    item["name"]
                    for item in components
                    if "/" in str(item.get("name", ""))
                ],
            }
        )
    return solutions


def build_evidence_matrix(
    intent: SearchIntent,
    solutions: list[dict[str, Any]],
    recommendations: list[dict[str, Any]],
) -> dict[str, Any]:
    repositories = {str(item.get("full_name")): item for item in recommendations}
    cells = []
    for solution in solutions:
        source_repositories = [
            repositories[name]
            for name in solution.get(
                "source_repositories", [solution.get("source_repository")]
            )
            if name in repositories
        ]
        for requirement in intent.requirements:
            matching = [
                item
                for repository in source_repositories
                for item in repository.get("criteria", [])
                if str(item.get("requirement_id")) == requirement.id
            ]
            matching.sort(
                key=lambda item: {
                    "satisfied": 2,
                    "unknown": 1,
                    "violated": 0,
                }.get(str(item.get("status")), 0),
                reverse=True,
            )
            criterion = matching[0] if matching else {}
            citations = []
            if criterion.get("evidence") and criterion.get("source_path"):
                citations.append(
                    {
                        "level": "documentation",
                        "quote": criterion["evidence"],
                        "path": criterion["source_path"],
                        "commit_sha": criterion.get("source_commit_sha"),
                    }
                )
            if criterion.get("implementation_evidence") and criterion.get(
                "implementation_source_path"
            ):
                citations.append(
                    {
                        "level": "implementation",
                        "quote": criterion["implementation_evidence"],
                        "path": criterion["implementation_source_path"],
                        "commit_sha": criterion.get(
                            "implementation_source_commit_sha"
                        ),
                    }
                )
            cells.append(
                {
                    "solution_id": solution["id"],
                    "requirement_id": requirement.id,
                    "status": criterion.get("status", "unknown"),
                    "implementation_status": criterion.get(
                        "implementation_status", "uncertain"
                    ),
                    "citations": citations,
                }
            )
    return {
        "requirements": [
            {"id": item.id, "description": item.description, "required": item.required}
            for item in intent.requirements
        ],
        "solutions": [
            {
                "id": item["id"],
                "title": item["title"],
                "source_repository": item["source_repository"],
            }
            for item in solutions
        ],
        "cells": cells,
    }
