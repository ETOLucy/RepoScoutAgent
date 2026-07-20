import unittest
from types import SimpleNamespace

from src.reposcout.search import (
    SearchIntent,
    compile_search_plan,
    parse_search_intent_with_llm,
    parse_search_intent_with_rules,
    relax_github_query,
)
from src.reposcout.search.models import ComponentRole, RequirementItem, SearchStrategy


class SearchPlanningTest(unittest.IsolatedAsyncioTestCase):
    async def test_llm_returns_requirements_and_keywords(self):
        expected = SearchIntent(
            goal="self-host family photos",
            requirements=[RequirementItem(id="face", description="支持人脸识别")],
            keywords=["self-hosted photos", "face recognition"],
        )

        async def parse(**_kwargs):
            return SimpleNamespace(output_parsed=expected)

        client = SimpleNamespace(responses=SimpleNamespace(parse=parse))

        result = await parse_search_intent_with_llm("找自托管照片项目", client, "test")

        self.assertEqual(result, expected)

    def test_rule_fallback_keeps_explicit_english_terms(self):
        intent = parse_search_intent_with_rules("找一个 Python LangGraph RAG 项目")
        self.assertEqual(intent.keywords, ["python", "langgraph", "rag"])

    def test_rule_fallback_translates_chinese_research_concepts(self):
        intent = parse_search_intent_with_rules(
            "根据自然语言发现 GitHub 仓库，支持多源搜索、项目比较和可验证引用"
        )

        self.assertEqual(intent.keywords[0], "repository discovery")
        self.assertIn("natural language search", intent.keywords)
        self.assertIn("multi source search", intent.keywords)
        self.assertIn("verifiable citations", intent.keywords)
        self.assertGreaterEqual(len(intent.requirements), 3)

    def test_compiler_uses_keywords_and_explicit_qualifiers(self):
        intent = SearchIntent(
            goal="photo app",
            keywords=["self-hosted photos", "face recognition", "docker"],
            language="TypeScript",
            minimum_stars=50,
            licenses=["MIT"],
            active_within_days=180,
        )

        plan = compile_search_plan(intent)
        query = plan.queries[0].query

        self.assertGreater(len(plan.queries), 1)
        self.assertEqual(len({item.fingerprint for item in plan.queries}), len(plan.queries))
        self.assertIn('"self-hosted photos"', query)
        self.assertIn("language:TypeScript", query)
        self.assertIn("stars:>=50", query)
        self.assertIn("license:mit", query)
        self.assertIn("pushed:>=", query)

    def test_compiler_preserves_llm_search_hypotheses(self):
        intent = SearchIntent(
            goal="self-host family photos",
            keywords=["self-hosted photos"],
            search_strategies=[
                SearchStrategy(
                    strategy_type="learning_reference_implementation",
                    terms=["self hosted photo management"],
                    rationale="Projects commonly describe the product category this way",
                    hypothesis="Well-documented implementations expose the architecture",
                    expected_signals=["architecture documentation"],
                    verifies=["face"],
                ),
                SearchStrategy(
                    strategy_type="alternative",
                    terms=["Google Photos alternative", "self hosted"],
                    rationale="Mature projects often position themselves as an alternative",
                ),
            ],
        )

        plan = compile_search_plan(intent)

        hypotheses = {
            item.strategy_type: item for item in plan.queries
        }
        self.assertIn("broad_recall", hypotheses)
        self.assertIn("learning_reference_implementation", hypotheses)
        self.assertIn("alternative", hypotheses)
        self.assertIn('"Google Photos alternative"', hypotheses["alternative"].query)
        self.assertNotIn("rules_fallback", {item.strategy_type for item in plan.queries})
        self.assertEqual(hypotheses["learning_reference_implementation"].verifies, ["face"])

    def test_compiler_does_not_require_every_capability_during_discovery(self):
        intent = SearchIntent(
            goal="self-hosted family photos",
            requirements=[
                RequirementItem(
                    id="face",
                    description="face recognition",
                    retrieval_terms=["face recognition"],
                ),
                RequirementItem(
                    id="mobile",
                    description="mobile auto backup",
                    retrieval_terms=["mobile backup"],
                ),
                RequirementItem(
                    id="docker",
                    description="Docker deployment",
                    retrieval_terms=["Docker"],
                ),
            ],
            keywords=["self-hosted photos", "face recognition", "mobile backup", "Docker"],
        )

        plan = compile_search_plan(intent)

        broad = next(item for item in plan.queries if item.strategy_type == "broad_recall")
        facets = [item for item in plan.queries if item.strategy_type == "requirement_facet"]
        self.assertEqual(broad.keywords, ["self-hosted photos"])
        self.assertEqual(len(facets), 3)
        self.assertFalse(all("Docker" in item.query for item in plan.queries))

    def test_compiler_rejects_missing_keywords(self):
        with self.assertRaisesRegex(ValueError, "没有可用于"):
            compile_search_plan(SearchIntent(goal="找项目"))

    def test_query_relaxation_preserves_qualifiers(self):
        query = '"self-hosted photos" "face recognition" docker archived:false stars:>=20'
        self.assertEqual(
            relax_github_query(query),
            '"self-hosted photos" archived:false stars:>=20',
        )

    def test_component_roles_receive_independent_query_budget(self):
        intent = SearchIntent(
            goal="photos",
            keywords=["self-hosted photos"],
            component_roles=[
                ComponentRole(
                    role="object_storage",
                    purpose="store originals",
                    search_terms=["S3 object storage"],
                    compatibility_interfaces=["s3"],
                    fulfills=["storage"],
                )
            ],
        )

        plan = compile_search_plan(intent)
        component_query = next(
            item for item in plan.queries if item.component_role == "object_storage"
        )

        self.assertEqual(component_query.strategy_type, "component_role")
        self.assertNotIn("language:", component_query.query)


if __name__ == "__main__":
    unittest.main()
