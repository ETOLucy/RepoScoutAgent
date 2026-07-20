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
        self.assertEqual(summaries[0]["status"], "completed")
        self.assertEqual(summaries[0]["query"], "find photos")
        self.assertEqual(restored, saved)
        self.assertIsNone(missing)

    def test_checkpoint_can_be_updated_resumed_and_completed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ResearchStore(Path(directory) / "research.db")
            saved = store.save_checkpoint(
                "conversation-1",
                "find an agent",
                {"interaction": {"status": "pending"}},
                {"raw_requirement": "find an agent", "interactive": True},
            )
            research_id = saved["research_id"]

            state = store.resume_state(research_id)
            updated = store.update_checkpoint(
                research_id,
                {**saved, "report": "revised"},
                {"raw_requirement": "find a Python agent", "interactive": True},
            )
            completed = store.complete(
                research_id, {**updated, "solutions": [{"id": "one"}]}
            )

            self.assertEqual(state["raw_requirement"], "find an agent")
            self.assertEqual(updated["research_id"], research_id)
            self.assertEqual(completed["research_id"], research_id)
            self.assertIsNone(store.resume_state(research_id))
            self.assertEqual(store.list()[0]["status"], "completed")
