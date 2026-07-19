from __future__ import annotations

import re
from collections import OrderedDict, defaultdict
from collections.abc import Iterable
from hashlib import sha256
from math import sqrt
from typing import Any

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]

from .search.models import RequirementItem, SearchIntent

_LATIN_TOKEN = re.compile(r"[a-z0-9][a-z0-9_.+/#-]*", re.I)
_CJK_SEQUENCE = re.compile(r"[\u3400-\u9fff]+")


class EmbeddingCache:
    def __init__(self, max_entries: int = 50_000, batch_size: int = 32) -> None:
        self._max_entries = max_entries
        self._batch_size = batch_size
        self._vectors: OrderedDict[tuple[str, str], list[float]] = OrderedDict()

    async def embed(
        self, embedding_client: Any, embedding_model: str, inputs: list[str]
    ) -> list[list[float]]:
        keys = [
            (embedding_model, sha256(item.encode()).hexdigest()) for item in inputs
        ]
        missing_by_key = {
            key: text
            for key, text in zip(keys, inputs, strict=True)
            if key not in self._vectors
        }
        missing = list(missing_by_key)
        for start in range(0, len(missing), self._batch_size):
            batch = missing[start : start + self._batch_size]
            response = await embedding_client.embeddings.create(
                model=embedding_model, input=[missing_by_key[key] for key in batch]
            )
            vectors = [item.embedding for item in response.data]
            if len(vectors) != len(batch):
                raise ValueError("embedding API returned an unexpected vector count")
            for key, vector in zip(batch, vectors, strict=True):
                self._vectors[key] = vector
        while len(self._vectors) > self._max_entries:
            self._vectors.popitem(last=False)
        for key in keys:
            self._vectors.move_to_end(key)
        return [self._vectors[key] for key in keys]


EMBEDDING_CACHE = EmbeddingCache()


def tokenize(text: str) -> list[str]:
    lowered = text.casefold()
    tokens: list[str] = []
    for token in _LATIN_TOKEN.findall(lowered):
        tokens.append(token)
        tokens.extend(part for part in re.split(r"[_.+/#-]+", token) if len(part) > 1)
    for sequence in _CJK_SEQUENCE.findall(lowered):
        if len(sequence) == 1:
            tokens.append(sequence)
        else:
            tokens.extend(sequence[index : index + 2] for index in range(len(sequence) - 1))
    return tokens


def requirement_query_views(
    requirement: RequirementItem, intent: SearchIntent
) -> list[str]:
    terms = requirement.retrieval_terms or intent.keywords
    views = [
        requirement.description,
        *(term for term in terms[:4]),
        f"{intent.goal}\nRequired capability: {requirement.description}",
    ]
    return list(dict.fromkeys(view.strip() for view in views if view.strip()))[:6]


def chunk_embedding_input(item: dict[str, str]) -> str:
    return "\n".join(
        [
            f"Source type: {item.get('source_type', 'unknown')}",
            f"File: {item.get('path', '')}",
            f"Heading: {item.get('heading', 'Introduction')}",
            f"Parsed static signals: {item.get('static_signals', '')}",
            item.get("content", ""),
        ]
    )


async def prewarm_retrieval_embeddings(
    intent: SearchIntent,
    chunks: list[dict[str, str]],
    embedding_client: Any,
    *,
    embedding_model: str,
) -> None:
    views = [
        view
        for requirement in intent.requirements
        for view in requirement_query_views(requirement, intent)
    ]
    inputs = list(dict.fromkeys([*(chunk_embedding_input(item) for item in chunks), *views]))
    if inputs:
        await EMBEDDING_CACHE.embed(embedding_client, embedding_model, inputs)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    denominator = sqrt(sum(value * value for value in left)) * sqrt(
        sum(value * value for value in right)
    )
    return numerator / denominator if denominator else 0.0


def _rank_dense(
    chunk_embeddings: list[list[float]], query_embedding: list[float]
) -> list[int]:
    return sorted(
        range(len(chunk_embeddings)),
        key=lambda index: _cosine_similarity(query_embedding, chunk_embeddings[index]),
        reverse=True,
    )


def _rank_lexical(corpus: list[list[str]], query: str) -> list[int]:
    query_tokens = tokenize(query)
    if not corpus or not query_tokens:
        return []
    scores = BM25Okapi(corpus).get_scores(query_tokens)
    query_set = set(query_tokens)
    return [
        index
        for index in sorted(range(len(corpus)), key=lambda item: scores[item], reverse=True)
        if query_set.intersection(corpus[index])
    ]


def _fuse_rankings(
    rankings: list[tuple[list[int], float]],
    *,
    candidate_k: int,
    rank_constant: int = 60,
) -> dict[int, float]:
    scores: defaultdict[int, float] = defaultdict(float)
    for ranking, weight in rankings:
        if weight <= 0:
            continue
        for rank, index in enumerate(ranking[:candidate_k], start=1):
            scores[index] += weight / (rank_constant + rank)
    if not scores:
        return {}
    maximum = max(scores.values())
    if maximum <= 0:
        return {}
    return {index: score / maximum for index, score in scores.items()}


def _select_mmr(
    relevance: dict[int, float],
    embeddings: list[list[float]],
    *,
    top_k: int,
    diversity: float,
) -> list[int]:
    remaining = set(relevance)
    selected: list[int] = []
    while remaining and len(selected) < top_k:
        def score(index: int) -> float:
            redundancy = max(
                (
                    max(0.0, _cosine_similarity(embeddings[index], embeddings[item]))
                    for item in selected
                ),
                default=0.0,
            )
            return (1 - diversity) * relevance[index] - diversity * redundancy

        chosen = max(remaining, key=lambda index: (score(index), relevance[index], -index))
        selected.append(chosen)
        remaining.remove(chosen)
    return selected


async def retrieve_for_requirements(
    intent: SearchIntent,
    chunks: list[dict[str, str]],
    embedding_client: Any,
    *,
    embedding_model: str,
    top_k: int = 3,
    candidate_k: int = 12,
    use_lexical: bool = True,
    lexical_weight: float = 1.0,
    dense_weight: float = 1.0,
    mmr_diversity: float = 0.25,
) -> dict[str, list[dict[str, str]]]:
    """Multi-query dense retrieval with optional BM25, weighted RRF, and MMR."""
    if not chunks or top_k <= 0:
        return {requirement.id: [] for requirement in intent.requirements}

    views_by_requirement = [
        requirement_query_views(requirement, intent) for requirement in intent.requirements
    ]
    flat_views = [view for views in views_by_requirement for view in views]
    chunk_inputs = [chunk_embedding_input(item) for item in chunks]
    inputs = chunk_inputs + flat_views
    vectors = await EMBEDDING_CACHE.embed(embedding_client, embedding_model, inputs)

    chunk_vectors = vectors[: len(chunks)]
    view_vectors = iter(vectors[len(chunks) :])
    corpus = [tokenize(item) for item in chunk_inputs]
    result: dict[str, list[dict[str, str]]] = {}
    for requirement, views in zip(intent.requirements, views_by_requirement, strict=True):
        requirement_vectors = [next(view_vectors) for _view in views]
        dense_share = dense_weight / max(1, len(requirement_vectors))
        rankings = [
            (_rank_dense(chunk_vectors, query_vector), dense_share)
            for query_vector in requirement_vectors
        ]
        if use_lexical:
            rankings.append((_rank_lexical(corpus, " ".join(views)), lexical_weight))
        relevance = _fuse_rankings(rankings, candidate_k=max(top_k, candidate_k))
        selected = _select_mmr(
            relevance,
            chunk_vectors,
            top_k=top_k,
            diversity=mmr_diversity,
        )
        result[requirement.id] = [chunks[index] for index in selected]
    return result


def retrieve_for_requirements_lexical(
    intent: SearchIntent,
    chunks: list[dict[str, str]],
    *,
    top_k: int = 3,
) -> dict[str, list[dict[str, str]]]:
    if not chunks or top_k <= 0:
        return {requirement.id: [] for requirement in intent.requirements}
    chunk_inputs = [chunk_embedding_input(item) for item in chunks]
    corpus = [tokenize(item) for item in chunk_inputs]
    result: dict[str, list[dict[str, str]]] = {}
    for requirement in intent.requirements:
        views = requirement_query_views(requirement, intent)
        ranking = _rank_lexical(corpus, " ".join(views))
        result[requirement.id] = [chunks[index] for index in ranking[:top_k]]
    return result


def unique_retrieved_chunks(
    retrieved: Iterable[list[dict[str, str]]],
) -> list[dict[str, str]]:
    unique: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for chunks in retrieved:
        for chunk in chunks:
            identity = (
                chunk.get("path", ""),
                chunk.get("heading", ""),
                chunk.get("content", ""),
            )
            if identity not in seen:
                seen.add(identity)
                unique.append(chunk)
    return unique


def format_requirement_context(
    intent: SearchIntent,
    retrieved: dict[str, list[dict[str, str]]],
) -> str:
    sections: list[str] = []
    for requirement in intent.requirements:
        chunks = retrieved.get(requirement.id, [])
        evidence = "\n\n".join(
            "\n".join(
                [
                    f"FILE: {item.get('path', '')}",
                    f"HEADING: {item.get('heading', 'Introduction')}",
                    f"COMMIT: {item.get('commit_sha', 'unknown')}",
                    f"SOURCE_TYPE: {item.get('source_type', 'unknown')}",
                    f"PARSED_SIGNALS: {item.get('static_signals', '')}",
                    item.get("content", ""),
                ]
            )
            for item in chunks
        )
        sections.append(
            f"REQUIREMENT {requirement.id}: {requirement.description}\n"
            f"RETRIEVED EVIDENCE:\n{evidence or '[no matching chunk]'}"
        )
    return "\n\n".join(sections)
