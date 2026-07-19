import tempfile
import unittest
from pathlib import Path

from src.reposcout.documents import DocumentCache, chunk_documents


class DocumentProcessingTest(unittest.TestCase):
    def test_markdown_chunks_keep_heading_metadata_and_code_block(self):
        content = """[![build](badge.svg)](ci)
# Project

Overview text.

## Install

Run this command:

```bash
docker compose up
```
"""
        chunks = chunk_documents(
            [
                {
                    "path": "README.md",
                    "url": "https://example.test/README.md",
                    "source_type": "readme",
                    "content": content,
                }
            ],
            repository="example/repo",
            commit_sha="abc123",
            max_chunk_chars=100,
        )

        self.assertEqual([item["heading"] for item in chunks], ["Project", "Project > Install"])
        self.assertIn("docker compose up", chunks[1]["content"])
        self.assertEqual(chunks[1]["commit_sha"], "abc123")
        self.assertEqual(chunks[1]["source_type"], "readme")
        self.assertNotIn("badge.svg", "".join(item["content"] for item in chunks))

    def test_duplicate_content_and_total_budget_are_limited(self):
        document = {
            "path": "README.md",
            "url": "https://example.test/README.md",
            "content": "# Same\n\nRepeated content",
        }
        chunks = chunk_documents(
            [document, {**document, "path": "docs/copy.md"}],
            repository="example/repo",
            commit_sha="abc123",
            max_total_chars=8,
        )

        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["content"], "Repeated")

    def test_cache_is_scoped_by_repository_and_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = DocumentCache(Path(directory))
            chunks = [{"path": "README.md", "content": "hello"}]
            cache.save("example/repo", "sha-one", chunks)

            self.assertEqual(cache.load("example/repo", "sha-one"), chunks)
            self.assertIsNone(cache.load("example/repo", "sha-two"))
            self.assertIsNone(cache.load("other/repo", "sha-one"))


if __name__ == "__main__":
    unittest.main()
