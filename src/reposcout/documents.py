from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

DEFAULT_CACHE_DIR = Path(".cache/repository_documents")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_BADGE = re.compile(r"^\s*\[?!?\[[^]]*]\([^)]*\)\]\([^)]*\)\s*$")
_NAVIGATION = re.compile(r"^\s*(?:[-*]\s*)?\[(?:home|back to top|目录|返回顶部)]", re.I)
_GENERATED = re.compile(r"(?:auto-generated|automatically generated|do not edit)", re.I)


def _clean_markdown(content: str) -> str:
    lines: list[str] = []
    generated_block = False
    for line in content.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        if "<!--" in line and _GENERATED.search(line):
            generated_block = True
        if generated_block:
            if "-->" in line:
                generated_block = False
            continue
        if _BADGE.match(line) or _NAVIGATION.match(line):
            continue
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


def _markdown_sections(content: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    heading_stack: list[tuple[int, str]] = []
    current_heading = "Introduction"
    current: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(current).strip()
        if text:
            sections.append((current_heading, text))
        current.clear()

    for line in _clean_markdown(content).splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match:
            flush()
            level = len(match.group(1))
            heading_stack[:] = [item for item in heading_stack if item[0] < level]
            heading_stack.append((level, match.group(2).strip()))
            current_heading = " > ".join(item[1] for item in heading_stack)
            continue
        current.append(line)
    flush()
    return sections


def _split_section(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    blocks = re.split(r"\n(?=\s*\n|[-*+]\s|\d+[.)]\s|```|~~~)", text)
    chunks: list[str] = []
    current = ""
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if len(block) > max_chars:
            pieces = [block[index : index + max_chars] for index in range(0, len(block), max_chars)]
        else:
            pieces = [block]
        for piece in pieces:
            candidate = f"{current}\n\n{piece}".strip() if current else piece
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = piece
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks


def chunk_documents(
    documents: list[dict[str, str]],
    *,
    repository: str,
    commit_sha: str,
    max_chunk_chars: int = 4_000,
    max_total_chars: int = 240_000,
) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    seen: set[str] = set()
    remaining = max_total_chars
    for document in documents:
        for heading, section in _markdown_sections(document["content"]):
            for text in _split_section(section, max_chunk_chars):
                normalized = re.sub(r"\s+", " ", text).strip().casefold()
                fingerprint = hashlib.sha256(normalized.encode()).hexdigest()
                if not normalized or fingerprint in seen or remaining <= 0:
                    continue
                seen.add(fingerprint)
                text = text[:remaining]
                chunks.append(
                    {
                        "repository": repository,
                        "path": document["path"],
                        "heading": heading,
                        "commit_sha": commit_sha,
                        "url": document["url"],
                        "source_type": document.get("source_type", "documentation"),
                        "content": text,
                    }
                )
                remaining -= len(text)
    return chunks


class DocumentCache:
    def __init__(self, directory: Path = DEFAULT_CACHE_DIR) -> None:
        self.directory = directory

    def _path(self, repository: str, commit_sha: str) -> Path:
        key = hashlib.sha256(f"{repository}@{commit_sha}".encode()).hexdigest()
        return self.directory / f"{key}.json"

    def load(self, repository: str, commit_sha: str) -> list[dict[str, str]] | None:
        path = self._path(repository, commit_sha)
        try:
            payload: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if isinstance(payload, dict):
            payload = payload.get("chunks")
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            return None
        return [{str(key): str(value) for key, value in item.items()} for item in payload]

    def save(
        self,
        repository: str,
        commit_sha: str,
        chunks: list[dict[str, str]],
        documents: list[dict[str, str]] | None = None,
    ) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self._path(repository, commit_sha)
        temporary = target.with_suffix(".tmp")
        payload = {
            "repository": repository,
            "commit_sha": commit_sha,
            "documents": documents or [],
            "chunks": chunks,
        }
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        temporary.replace(target)


def source_type_for_path(path: str) -> str:
    name = PurePosixPath(path).name.lower()
    return "readme" if name.startswith("readme") else "documentation"
