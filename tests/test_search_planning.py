import unittest
from types import SimpleNamespace

from src.reposcout.search import (
    SearchIntent,
    compile_search_plan,
    parse_search_intent_with_llm,
    parse_search_intent_with_rules,
    relax_github_query,
)
from src.reposcout.search.models import RequirementItem


class SearchPlanningTest(unittest.TestCase):
    def test_llm_returns_requirements_and_keywords(self):
        expected = SearchIntent(
            goal="self-host family photos",
            requirements=[RequirementItem(id="face", description="支持人脸识别")],
            keywords=["self-hosted photos", "face recognition"],
        )
        client = SimpleNamespace(
            responses=SimpleNamespace(
                parse=lambda **_kwargs: SimpleNamespace(output_parsed=expected)
            )
        )

        result = parse_search_intent_with_llm("找自托管照片项目", client, "test")

        self.assertEqual(result, expected)

    def test_rule_fallback_keeps_explicit_english_terms(self):
        intent = parse_search_intent_with_rules("找一个 Python LangGraph RAG 项目")
        self.assertEqual(intent.keywords, ["python", "langgraph", "rag"])

    def test_compiler_uses_keywords_and_explicit_qualifiers(self):
        intent = SearchIntent(
            goal="photo app",
            keywords=["self-hosted photos", "face recognition", "docker"],
            language="TypeScript",
            minimum_stars=50,
            licenses=["MIT"],
            active_within_days=180,
        )

        query = compile_search_plan(intent).queries[0].query

        self.assertIn('"self-hosted photos"', query)
        self.assertIn("language:TypeScript", query)
        self.assertIn("stars:>=50", query)
        self.assertIn("license:mit", query)
        self.assertIn("pushed:>=", query)

    def test_compiler_rejects_missing_keywords(self):
        with self.assertRaisesRegex(ValueError, "没有可用于"):
            compile_search_plan(SearchIntent(goal="找项目"))

    def test_query_relaxation_preserves_qualifiers(self):
        query = '"self-hosted photos" "face recognition" docker archived:false stars:>=20'
        self.assertEqual(
            relax_github_query(query),
            "self-hosted face archived:false stars:>=20",
        )


if __name__ == "__main__":
    unittest.main()
