import unittest

from src.reposcout.conversations import ConversationStore


class ConversationStoreTest(unittest.TestCase):
    def test_later_turns_share_context_and_can_override_constraints(self):
        store = ConversationStore()
        conversation_id, first, turn = store.begin_turn(None, "find a Python RAG project")
        _, second, next_turn = store.begin_turn(conversation_id, "Rust instead, for learning")

        self.assertEqual(turn, 1)
        self.assertEqual(next_turn, 2)
        self.assertIn("find a Python RAG project", second)
        self.assertIn("Rust instead, for learning", second)
        self.assertIn("refine or override", first)

    def test_clarification_is_included_once(self):
        store = ConversationStore()
        conversation_id, _, _ = store.begin_turn(None, "find a database")
        store.record_clarification(conversation_id, "Embedded or distributed?")

        _, context, _ = store.begin_turn(conversation_id, "Embedded")
        _, later_context, _ = store.begin_turn(conversation_id, "Prefer Rust")

        self.assertIn("Embedded or distributed?", context)
        self.assertNotIn("Embedded or distributed?", later_context)

    def test_reset_discards_previous_turns(self):
        store = ConversationStore()
        conversation_id, _, _ = store.begin_turn("session", "first request")
        store.reset(conversation_id)
        _, context, turn = store.begin_turn(conversation_id, "new request")

        self.assertEqual(turn, 1)
        self.assertNotIn("first request", context)


if __name__ == "__main__":
    unittest.main()
