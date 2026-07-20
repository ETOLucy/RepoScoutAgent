import tempfile
import unittest
from pathlib import Path

from src.reposcout.research import ResearchStore


class ResearchStoreTest(unittest.TestCase):
    def test_saves_lists_and_restores_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ResearchStore(Path(directory) / "research.db")
            saved = store.save(
                "conversation-1",
                "find photos",
                {
                    "solutions": [{"id": "solution-1"}],
                    "evidence_matrix": {"cells": [{"status": "satisfied"}]},
                },
            )

            summaries = store.list()
            restored = store.get(saved["research_id"])
            missing = store.get("missing")

        self.assertEqual(summaries[0]["solution_count"], 1)
        self.assertEqual(summaries[0]["query"], "find photos")
        self.assertEqual(restored, saved)
        self.assertIsNone(missing)
