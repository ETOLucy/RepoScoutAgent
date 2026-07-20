import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.reposcout.conversations import ConversationStore


class ConversationStoreTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.database_path = Path(self.directory.name) / "conversations.db"

    def tearDown(self):
        self.directory.cleanup()

    def store(self):
        return ConversationStore(self.database_path)

    def test_later_turns_share_context_and_can_override_constraints(self):
        store = self.store()
        conversation_id, first, turn = store.begin_turn(None, "find a Python RAG project")
        _, second, next_turn = store.begin_turn(conversation_id, "Rust instead, for learning")

        self.assertEqual(turn, 1)
        self.assertEqual(next_turn, 2)
        self.assertIn("find a Python RAG project", second)
        self.assertIn("Rust instead, for learning", second)
        self.assertEqual(first, "find a Python RAG project")

    def test_standalone_goal_replaces_active_context(self):
        store = self.store()
        conversation_id, _, _ = store.begin_turn(None, "想找自托管照片项目")

        _, context, turn = store.begin_turn(
            conversation_id, "想找一个 GitHub repo 推荐项目，尽量可以实操"
        )

        self.assertEqual(turn, 2)
        self.assertNotIn("照片", context)
        self.assertEqual(context, "想找一个 GitHub repo 推荐项目，尽量可以实操")

    def test_explicit_context_mode_overrides_auto_detection(self):
        store = self.store()
        conversation_id, _, _ = store.begin_turn(None, "find a photo app")

        _, refined, _ = store.begin_turn(conversation_id, "mobile", "refine")
        _, replaced, _ = store.begin_turn(conversation_id, "Docker", "new")

        self.assertIn("find a photo app", refined)
        self.assertNotIn("photo", replaced)
        self.assertEqual(replaced, "Docker")

    def test_clarification_is_included_once(self):
        store = self.store()
        conversation_id, _, _ = store.begin_turn(None, "find a database")
        store.record_clarification(conversation_id, "Embedded or distributed?")

        _, context, _ = store.begin_turn(conversation_id, "Embedded")
        _, later_context, _ = store.begin_turn(conversation_id, "Prefer Rust")

        self.assertIn("Embedded or distributed?", context)
        self.assertNotIn("Embedded or distributed?", later_context)

    def test_reset_discards_previous_turns(self):
        store = self.store()
        conversation_id, _, _ = store.begin_turn("session", "first request")
        store.reset(conversation_id)
        _, context, turn = store.begin_turn(conversation_id, "new request")

        self.assertEqual(turn, 1)
        self.assertNotIn("first request", context)

    def test_history_survives_new_store_instance(self):
        store = self.store()
        conversation_id, _, _ = store.begin_turn(None, "find a local agent")
        store.record_assistant(
            conversation_id, "I found one", {"report": "I found one"}
        )

        restored = self.store().get(conversation_id)
        summaries = self.store().list()

        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(
            [message["role"] for message in restored["messages"]],
            ["user", "assistant"],
        )
        self.assertEqual(restored["messages"][1]["payload"]["report"], "I found one")
        self.assertEqual(summaries[0]["id"], conversation_id)


if __name__ == "__main__":
    unittest.main()
