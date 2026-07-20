import unittest

from src.reposcout.architecture import infer_component_roles
from src.reposcout.compatibility import extract_compatibility_evidence
from src.reposcout.search.models import RequirementItem, SearchIntent


class CompatibilityTest(unittest.TestCase):
    def test_infers_independent_roles_from_atomic_requirements(self):
        intent = SearchIntent(
            goal="self-hosted photos",
            requirements=[
                RequirementItem(id="mobile", description="支持手机自动备份"),
                RequirementItem(id="storage", description="使用 S3 对象存储"),
                RequirementItem(id="tls", description="通过反向代理提供 HTTPS"),
            ],
            keywords=["photos"],
        )

        roles = infer_component_roles(intent)

        self.assertEqual(
            {item.role for item in roles},
            {"mobile_sync", "object_storage", "reverse_proxy"},
        )

    def test_extracts_interfaces_and_named_companions_with_citations(self):
        evidence = extract_compatibility_evidence(
            [
                {
                    "path": "docs/sync.md",
                    "url": "https://example.test/sync",
                    "commit_sha": "abc",
                    "content": "Use PhotoSync to upload through WebDAV.",
                }
            ]
        )

        self.assertEqual(evidence["interfaces"]["webdav"][0]["path"], "docs/sync.md")
        self.assertEqual(
            evidence["named_components"]["PhotoSync"][0]["quote"], "PhotoSync"
        )
