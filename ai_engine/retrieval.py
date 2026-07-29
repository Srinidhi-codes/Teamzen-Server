"""
Hybrid policy retrieval: pgvector semantic search + Postgres full-text, fused with RRF.
"""
from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank
from pgvector.django import L2Distance

from ai_engine.models import PolicyDocument


CITATIONS_MARKER = "---CITATIONS_JSON---"
RRF_K = 60
DEFAULT_BRANCH_K = 8
DEFAULT_TOP_N = 5


def get_policy_file_url(policy_file) -> str | None:
    """Signed Cloudinary URL for a PolicyFile, matching PolicyFileSerializer."""
    if not policy_file or not policy_file.file:
        return None
    try:
        import cloudinary.utils

        raw_url = policy_file.file.url
        public_id = policy_file.file.public_id

        if hasattr(policy_file.file, "url") and "." in raw_url:
            ext = raw_url.split(".")[-1].split("?")[0]
            if not public_id.endswith(f".{ext}"):
                public_id = f"{public_id}.{ext}"

        version = None
        if "/v" in raw_url:
            version = raw_url.split("/v")[-1].split("/")[0]

        return cloudinary.utils.cloudinary_url(
            public_id,
            resource_type="raw",
            type="upload",
            version=version,
            sign_url=True,
            secure=True,
        )[0]
    except Exception:
        return policy_file.file.url if hasattr(policy_file.file, "url") else None


def _base_queryset(organization_id: int):
    return PolicyDocument.objects.filter(
        policy_file__organization_id=organization_id,
        policy_file__is_active=True,
        policy_file__is_processed=True,
    ).select_related("policy_file")


def _doc_to_hit(doc: PolicyDocument, score: float, match_types: set[str]) -> dict[str, Any]:
    page = doc.page_number
    if page is None and isinstance(doc.metadata, dict):
        page = doc.metadata.get("page_number")
    file_id = doc.policy_file_id
    return {
        "chunk_id": doc.id,
        "title": doc.title,
        "content": doc.content,
        "page_number": page,
        "file_id": file_id,
        "file_url": get_policy_file_url(doc.policy_file) if doc.policy_file else None,
        "score": round(score, 6),
        "match_type": "+".join(sorted(match_types)) if match_types else "unknown",
    }


def _rrf_merge(
    ranked_lists: list[list[PolicyDocument]],
    top_n: int,
) -> list[tuple[PolicyDocument, float, set[str]]]:
    """Reciprocal Rank Fusion across ordered result lists."""
    scores: dict[int, float] = {}
    match_types: dict[int, set[str]] = {}
    docs_by_id: dict[int, PolicyDocument] = {}
    labels = ["vector", "fts"]

    for list_idx, ranked in enumerate(ranked_lists):
        label = labels[list_idx] if list_idx < len(labels) else f"list{list_idx}"
        for rank, doc in enumerate(ranked, start=1):
            scores[doc.id] = scores.get(doc.id, 0.0) + 1.0 / (RRF_K + rank)
            match_types.setdefault(doc.id, set()).add(label)
            docs_by_id[doc.id] = doc

    ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [
        (docs_by_id[doc_id], score, match_types[doc_id])
        for doc_id, score in ordered
    ]


def hybrid_search(
    query: str,
    organization_id: int,
    *,
    branch_k: int = DEFAULT_BRANCH_K,
    top_n: int = DEFAULT_TOP_N,
    vector_distance_lt: float | None = 0.85,
) -> list[dict[str, Any]]:
    """
    Run vector + full-text retrieval and fuse with RRF.
    Returns structured citation-ready hits.
    """
    if not query or not organization_id:
        return []

    qs = _base_queryset(organization_id)
    if not qs.exists():
        return []

    # --- Vector branch ---
    vector_docs: list[PolicyDocument] = []
    try:
        from langchain_openai import OpenAIEmbeddings

        embeddings = OpenAIEmbeddings(openai_api_key=settings.OPENAI_API_KEY)
        query_embedding = embeddings.embed_query(query)
        vector_qs = qs.annotate(distance=L2Distance("embedding", query_embedding))
        if vector_distance_lt is not None:
            vector_qs = vector_qs.filter(distance__lt=vector_distance_lt)
        vector_docs = list(vector_qs.order_by("distance")[:branch_k])
    except Exception:
        vector_docs = []

    # --- FTS branch ---
    fts_docs: list[PolicyDocument] = []
    try:
        search_query = SearchQuery(query, search_type="websearch", config="english")
        fts_qs = (
            qs.exclude(search_vector=None)
            .annotate(rank=SearchRank("search_vector", search_query))
            .filter(search_vector=search_query)
            .order_by("-rank")[:branch_k]
        )
        fts_docs = list(fts_qs)
    except Exception:
        fts_docs = []

    # If FTS empty (e.g. unprocessed search_vector), fall back to vector-only
    ranked_lists = [vector_docs, fts_docs]
    if not vector_docs and not fts_docs:
        return []
    if not vector_docs:
        ranked_lists = [fts_docs]
    elif not fts_docs:
        ranked_lists = [vector_docs]

    merged = _rrf_merge(ranked_lists, top_n=top_n)
    return [_doc_to_hit(doc, score, types) for doc, score, types in merged]


def format_hits_for_llm(hits: list[dict[str, Any]]) -> str:
    """Human-readable excerpts for the agent, with a machine-parseable citations trailer."""
    if not hits:
        return "No policy documents found for your organization."

    parts = []
    citations = []
    for hit in hits:
        page = hit.get("page_number")
        page_label = f" | Page: {page}" if page else ""
        parts.append(
            f"Source: {hit['title']}{page_label} | file_id: {hit.get('file_id')}\n"
            f"Content: {hit['content']}"
        )
        citations.append(
            {
                "title": hit["title"],
                "page_number": hit.get("page_number"),
                "file_id": hit.get("file_id"),
                "file_url": hit.get("file_url"),
                "chunk_id": hit.get("chunk_id"),
                "score": hit.get("score"),
                "match_type": hit.get("match_type"),
            }
        )

    body = "\n\n---\n\n".join(parts)
    return f"{body}\n\n{CITATIONS_MARKER}\n{json.dumps(citations)}"


def parse_citations_from_tool_output(output: Any) -> list[dict[str, Any]]:
    """Extract citation list from search_policies tool output string."""
    if output is None:
        return []

    text = ""
    if isinstance(output, str):
        text = output
    elif hasattr(output, "content"):
        content = output.content
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            # Some LangChain message formats use content blocks
            text = " ".join(
                block.get("text", "") if isinstance(block, dict) else str(block)
                for block in content
            )
        else:
            text = str(content)
    else:
        text = str(output)

    if CITATIONS_MARKER not in text:
        return []

    raw = text.split(CITATIONS_MARKER, 1)[1].strip()
    # Tool output may append extra whitespace or trailing content
    if "\n" in raw:
        # Take the first JSON array line/block
        raw = raw.strip()
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        # Attempt to extract first JSON array
        start = raw.find("[")
        end = raw.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(raw[start : end + 1])
                return data if isinstance(data, list) else []
            except json.JSONDecodeError:
                return []
        return []
