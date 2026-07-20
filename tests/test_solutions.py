import unittest

from src.reposcout.search.models import ComponentRole, RequirementItem, SearchIntent
from src.reposcout.solutions import build_evidence_matrix, build_solutions


class SolutionTest(unittest.TestCase):
    def test_builds_actionable_solution_from_verified_repository(self):
        intent = SearchIntent(
            goal="self-hosted photos",
            requirements=[
                RequirementItem(id="face", description="支持人脸识别"),
                RequirementItem(id="docker", description="支持 Docker 部署"),
                RequirementItem(id="mobile", description="支持手机自动备份"),
            ],
            keywords=["photos"],
        )
        recommendation = {
            "full_name": "example/photo-app",
            "url": "https://github.com/example/photo-app",
            "score": 80,
            "summary": "照片管理主组件",
            "match_kind": "eligible",
            "criteria": [
                {
                    "requirement_id": "face",
                    "status": "satisfied",
                    "implementation_status": "implemented",
                    "evidence": "face recognition",
                    "source_path": "README.md",
                    "source_commit_sha": "abc123",
                },
                {
                    "requirement_id": "docker",
                    "status": "satisfied",
                    "implementation_status": "documented_only",
                },
                {
                    "requirement_id": "mobile",
                    "status": "unknown",
                    "implementation_status": "uncertain",
                },
            ],
        }

        solution = build_solutions(intent, [recommendation])[0]

        self.assertEqual(solution["components"][0]["role"], "primary")
        self.assertEqual(solution["deployment_status"], "documented")
        self.assertEqual(solution["evidence_confidence"], "partial")
        self.assertEqual(solution["gaps"][0]["requirement_id"], "mobile")
        self.assertIn("补齐或验证缺口", solution["rollout_steps"][-1])

        matrix = build_evidence_matrix(intent, [solution], [recommendation])
        face = next(
            item for item in matrix["cells"] if item["requirement_id"] == "face"
        )
        self.assertEqual(face["status"], "satisfied")
        self.assertEqual(face["citations"][0]["path"], "README.md")
        self.assertEqual(matrix["requirements"][0]["description"], "支持人脸识别")

    def test_near_match_is_explicitly_a_tradeoff_solution(self):
        intent = SearchIntent(
            goal="deployment",
            requirements=[RequirementItem(id="docker", description="Docker deployment")],
            keywords=["deployment"],
        )
        recommendation = {
            "full_name": "example/manual-install",
            "match_kind": "near_miss",
            "criteria": [
                {
                    "requirement_id": "docker",
                    "status": "violated",
                    "implementation_status": "contradicted",
                }
            ],
        }

        solution = build_solutions(intent, [recommendation])[0]

        self.assertTrue(solution["title"].startswith("条件取舍方案"))
        self.assertEqual(solution["deployment_status"], "blocked")
        self.assertEqual(solution["gaps"][0]["action"], "需要替代组件或调整此项要求")

    def test_combines_components_only_with_shared_interface_evidence(self):
        intent = SearchIntent(
            goal="photo backup",
            requirements=[
                RequirementItem(id="mobile", description="手机自动备份")
            ],
            keywords=["photos"],
            component_roles=[
                ComponentRole(
                    role="mobile_sync",
                    purpose="mobile upload",
                    search_terms=["mobile WebDAV"],
                    compatibility_interfaces=["webdav"],
                    fulfills=["mobile"],
                )
            ],
        )
        primary = {
            "full_name": "example/photos",
            "url": "https://github.com/example/photos",
            "score": 60,
            "match_kind": "eligible",
            "criteria": [
                {
                    "requirement_id": "mobile",
                    "status": "unknown",
                    "implementation_status": "uncertain",
                }
            ],
            "compatibility": {
                "interfaces": {"webdav": [{"path": "README.md", "quote": "WebDAV"}]},
                "named_components": {},
            },
        }
        companion = {
            "full_name": "example/mobile-sync",
            "url": "https://github.com/example/mobile-sync",
            "score": 50,
            "component_roles": ["mobile_sync"],
            "criteria": [
                {
                    "requirement_id": "mobile",
                    "status": "satisfied",
                    "implementation_status": "documented_only",
                    "evidence": "automatic upload",
                    "source_path": "README.md",
                }
            ],
            "compatibility": {
                "interfaces": {"webdav": [{"path": "docs/webdav.md", "quote": "WebDAV"}]},
                "named_components": {},
            },
        }

        solution = build_solutions(intent, [primary], [primary, companion])[0]
        matrix = build_evidence_matrix(intent, [solution], [primary, companion])

        self.assertEqual(solution["components"][1]["role"], "mobile_sync")
        self.assertEqual(
            solution["components"][1]["compatibility_status"], "interface_verified"
        )
        self.assertEqual(solution["components"][1]["shared_interfaces"], ["webdav"])
        self.assertEqual(matrix["cells"][0]["status"], "satisfied")

    def test_primary_documented_photosync_is_a_single_sided_compatibility_claim(self):
        intent = SearchIntent(
            goal="photo backup",
            requirements=[
                RequirementItem(id="mobile", description="手机自动备份")
            ],
            keywords=["photos"],
        )
        primary = {
            "full_name": "example/photos",
            "score": 50,
            "match_kind": "eligible",
            "criteria": [],
            "compatibility": {
                "interfaces": {"webdav": [{"path": "docs/sync.md"}]},
                "named_components": {
                    "PhotoSync": [
                        {
                            "path": "docs/sync.md",
                            "url": "https://github.com/example/photos/docs/sync.md",
                            "quote": "PhotoSync",
                        }
                    ]
                },
            },
        }

        solution = build_solutions(intent, [primary])[0]
        photosync = next(
            item for item in solution["components"] if item["name"] == "PhotoSync"
        )

        self.assertEqual(photosync["role"], "mobile_sync")
        self.assertEqual(
            photosync["compatibility_status"], "documented_by_primary"
        )


if __name__ == "__main__":
    unittest.main()
