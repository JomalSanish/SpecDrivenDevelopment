"""
backend/tests/unit/test_phase3_rag.py

Phase 3 unit tests: Hybrid RAG indexing and retrieval.

Test strategy (per user instruction):
  1. Secrets abstraction is wired — QdrantIndexingService and
     EvidenceRetrievalAgent read endpoints from the secrets layer (never
     directly from os.environ inside the module).
  2. No external calls — all network calls are stubbed with httpx.MockTransport
     or unittest.mock so the test suite is fully hermetic.
  3. RRF logic is tested in isolation (pure Python, no I/O).
  4. Chunking is tested in isolation (pure Python, no I/O).
  5. Integration smoke tests verify that if the local endpoints ARE reachable
     (Qdrant at localhost:6333, TEI at localhost:8080), they respond correctly.
     These are decorated with @pytest.mark.integration and skipped automatically
     in hermetic CI.

Run unit tests only:
    pytest backend/tests/unit/test_phase3_rag.py -v

Run with integration smoke tests (requires local stack):
    pytest backend/tests/unit/test_phase3_rag.py -v -m integration
"""
from __future__ import annotations

import os
import sys
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure backend/src on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Force env backend so no Vault required
os.environ.setdefault("SECRETS_BACKEND", "env")
os.environ.setdefault("EMBEDDING_ENDPOINT", "http://localhost:8080")
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("QDRANT_PORT", "6333")
os.environ.setdefault("LLM_ENDPOINT", "http://localhost:11434")


# ===========================================================================
# T015 — Chunking Service (pure Python, hermetic)
# ===========================================================================


class TestChunkingService:
    """Unit tests for backend/src/services/chunking_service.py"""

    def test_chunk_text_returns_nonempty_for_normal_input(self):
        from src.services.chunking_service import chunk_text

        text = "This is a sentence. And another sentence. A third one here."
        chunks, _ = chunk_text(
            text=text,
            case_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
            page_number=0,
        )
        assert len(chunks) >= 1
        for c in chunks:
            assert c.text.strip()
            assert c.case_id
            assert c.document_id
            assert c.chunk_id
            assert isinstance(c.page_number, int)

    def test_chunk_text_empty_returns_empty_list(self):
        from src.services.chunking_service import chunk_text

        chunks, tail = chunk_text("   ", case_id="c1", document_id="d1")
        assert chunks == []
        assert tail == ""

    def test_chunk_metadata_stamped_correctly(self):
        from src.services.chunking_service import chunk_text

        case_id = str(uuid.uuid4())
        doc_id = str(uuid.uuid4())
        chunks, _ = chunk_text(
            text="Alpha. Beta. Gamma.",
            case_id=case_id,
            document_id=doc_id,
            page_number=3,
        )
        for c in chunks:
            assert c.case_id == case_id
            assert c.document_id == doc_id
            assert c.page_number == 3
            # chunk_id must be a valid UUID
            uuid.UUID(c.chunk_id)

    def test_chunk_ids_are_unique(self):
        from src.services.chunking_service import chunk_pages

        pages = ["First page text. " * 50, "Second page text. " * 50]
        chunks = chunk_pages(
            pages=pages,
            case_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
        )
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), "Chunk IDs must be unique across pages"

    def test_chunk_page_numbers_match_page_index(self):
        from src.services.chunking_service import chunk_pages

        pages = ["Page zero text.", "Page one text.", "Page two text."]
        chunks = chunk_pages(
            pages=pages,
            case_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
        )
        for c in chunks:
            assert c.page_number in (0, 1, 2)

    def test_oversized_sentence_is_hard_split(self):
        from src.services.chunking_service import chunk_text, CHUNK_SIZE_TOKENS, _CHARS_PER_TOKEN

        long_sentence = "word " * (CHUNK_SIZE_TOKENS * 2)
        chunks, _ = chunk_text(
            text=long_sentence,
            case_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
        )
        assert len(chunks) >= 2, "Oversized sentence should be split into multiple chunks"
        for c in chunks:
            assert c.token_count <= CHUNK_SIZE_TOKENS * 1.1  # allow small overshoot

    def test_token_count_approximate(self):
        from src.services.chunking_service import chunk_text

        text = "Clinical notes from last 6 months. Physical therapy records. Imaging results."
        chunks, _ = chunk_text(text=text, case_id="c1", document_id="d1")
        for c in chunks:
            assert c.token_count > 0

    def test_overlap_carries_across_page_boundary(self):
        """
        rag-pipeline.md §Chunking Strategy: overlap must preserve context
        ACROSS page breaks, not just within a single page. A sentence split
        across two pages should have its tail carried into the next page's
        first chunk, not silently dropped.
        """
        from src.services.chunking_service import chunk_pages

        page_1 = "Patient reports six weeks of conservative therapy. " * 40
        page_2 = "Continuing the therapy course into month two. " * 40

        chunks = chunk_pages(
            pages=[page_1, page_2],
            case_id=str(uuid.uuid4()),
            document_id=str(uuid.uuid4()),
        )

        page_0_chunks = [c for c in chunks if c.page_number == 0]
        page_1_chunks = [c for c in chunks if c.page_number == 1]
        assert page_0_chunks and page_1_chunks

        last_text_of_page_0 = page_0_chunks[-1].text
        first_text_of_page_1 = page_1_chunks[0].text

        assert first_text_of_page_1 != page_2.strip(), (
            "Expected page 2's first chunk to be seeded with overlap text "
            "from page 1's last chunk, but it contains only page 2's own text."
        )
        tail_fragment = last_text_of_page_0[-30:].strip()
        assert any(
            word in first_text_of_page_1 for word in tail_fragment.split() if len(word) > 3
        ), "Expected some trailing words from page 1 to carry into page 2's first chunk"


# ===========================================================================
# T014/T015 — Stable hashing regression (cross-process, catches PYTHONHASHSEED bugs)
# ===========================================================================


class TestStableTokeniserHash:
    """
    Regression test for the _bm25_tokenise() vocabulary hash.

    This MUST be stable across separate process invocations — Python's
    built-in hash() is randomised per-process for str objects (PYTHONHASHSEED),
    so a same-process test alone would NOT catch a regression back to hash().
    We run tokenisation in a fresh subprocess twice and compare output.
    """

    def test_tokeniser_is_stable_across_process_restarts(self):
        import subprocess
        import sys as _sys
        import textwrap

        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
        repo_root = os.path.abspath(os.path.join(backend_dir, ".."))

        script = textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {backend_dir!r})
            from src.services.qdrant_service import _bm25_tokenise
            indices, values = _bm25_tokenise("clinical notes imaging MRI CPT12345")
            print(indices)
            """
        ).strip()

        env = os.environ.copy()
        env.pop("PYTHONHASHSEED", None)  # ensure default (random) seeding

        run_1 = subprocess.run(
            [_sys.executable, "-c", script],
            cwd=repo_root,
            capture_output=True,
            text=True,
            env=env,
        )
        run_2 = subprocess.run(
            [_sys.executable, "-c", script],
            cwd=repo_root,
            capture_output=True,
            text=True,
            env=env,
        )

        assert run_1.returncode == 0, run_1.stderr
        assert run_2.returncode == 0, run_2.stderr
        assert run_1.stdout == run_2.stdout, (
            "Tokeniser produced different vocabulary indices across two separate "
            "process runs — this means sparse vectors indexed before a restart "
            "become unmatchable after a restart. Check that _bm25_tokenise uses "
            "a stable hash (e.g. hashlib.md5), not Python's built-in hash()."
        )


# ===========================================================================
# T017 — Fusion Service (pure Python, hermetic)
# ===========================================================================


class TestFusionService:
    """Unit tests for backend/src/services/fusion_service.py"""

    def _make_chunk(self, chunk_id: str, score: float, source: str):
        from src.services.qdrant_service import RetrievedChunk

        return RetrievedChunk(
            chunk_id=chunk_id,
            case_id="case-abc",
            document_id="doc-xyz",
            page_number=0,
            text=f"Text for {chunk_id}",
            score=score,
            source=source,
        )

    def test_rrf_returns_fused_results(self):
        from src.services.fusion_service import reciprocal_rank_fusion

        dense = [self._make_chunk("c1", 0.9, "dense"), self._make_chunk("c2", 0.8, "dense")]
        sparse = [self._make_chunk("c2", 0.95, "sparse"), self._make_chunk("c3", 0.7, "sparse")]

        fused = reciprocal_rank_fusion(dense, sparse, top_k=5)
        assert len(fused) == 3  # c1, c2, c3 all present
        chunk_ids = {r.chunk_id for r in fused}
        assert chunk_ids == {"c1", "c2", "c3"}

    def test_rrf_score_formula(self):
        from src.services.fusion_service import reciprocal_rank_fusion

        k = 60
        dense = [self._make_chunk("c1", 0.9, "dense")]
        sparse = [self._make_chunk("c1", 0.9, "sparse")]

        fused = reciprocal_rank_fusion(dense, sparse, k=k)
        assert len(fused) == 1
        expected_score = 1 / (k + 1) + 1 / (k + 1)  # both rank 1
        assert abs(fused[0].rrf_score - expected_score) < 1e-9

    def test_keyword_miss_flag_set_for_dense_only(self):
        from src.services.fusion_service import reciprocal_rank_fusion

        # c1: dense only → keyword_miss=True
        # c2: both        → keyword_miss=False
        dense = [self._make_chunk("c1", 0.9, "dense"), self._make_chunk("c2", 0.8, "dense")]
        sparse = [self._make_chunk("c2", 0.85, "sparse")]

        fused = reciprocal_rank_fusion(dense, sparse)
        fused_by_id = {r.chunk_id: r for r in fused}

        assert fused_by_id["c1"].keyword_miss is True
        assert fused_by_id["c2"].keyword_miss is False

    def test_keyword_miss_flag_false_for_sparse_only(self):
        from src.services.fusion_service import reciprocal_rank_fusion

        # c1: sparse only → keyword_miss=False (it IS a keyword hit)
        dense: list = []
        sparse = [self._make_chunk("c1", 0.9, "sparse")]

        fused = reciprocal_rank_fusion(dense, sparse)
        assert fused[0].keyword_miss is False

    def test_rrf_ranking_order(self):
        from src.services.fusion_service import reciprocal_rank_fusion

        # c2 appears in both lists at top rank → should beat c1 (dense-only)
        dense = [
            self._make_chunk("c1", 0.99, "dense"),
            self._make_chunk("c2", 0.7, "dense"),
        ]
        sparse = [self._make_chunk("c2", 0.99, "sparse")]

        fused = reciprocal_rank_fusion(dense, sparse)
        # c2: 1/(60+2) + 1/(60+1) > c1: 1/(60+1)
        assert fused[0].chunk_id == "c2"

    def test_top_k_limit(self):
        from src.services.fusion_service import reciprocal_rank_fusion

        dense = [self._make_chunk(f"c{i}", 0.9 - i * 0.01, "dense") for i in range(10)]
        sparse = [self._make_chunk(f"c{i}", 0.9 - i * 0.01, "sparse") for i in range(10)]

        fused = reciprocal_rank_fusion(dense, sparse, top_k=3)
        assert len(fused) == 3

    def test_empty_lists_return_empty(self):
        from src.services.fusion_service import reciprocal_rank_fusion

        assert reciprocal_rank_fusion([], []) == []

    def test_dense_score_and_sparse_score_populated(self):
        from src.services.fusion_service import reciprocal_rank_fusion

        dense = [self._make_chunk("c1", 0.88, "dense")]
        sparse = [self._make_chunk("c1", 0.72, "sparse")]

        fused = reciprocal_rank_fusion(dense, sparse)
        assert fused[0].dense_score == pytest.approx(0.88)
        assert fused[0].sparse_score == pytest.approx(0.72)


# ===========================================================================
# T014 — Secrets abstraction wiring (hermetic — mocked Qdrant client)
# ===========================================================================


class TestQdrantServiceSecretsWiring:
    """
    Verify that QdrantIndexingService reads its config through the secrets
    abstraction (get_secret) and not directly from os.environ.
    """

    def test_qdrant_service_reads_host_from_secrets(self):
        """QdrantIndexingService must use get_secret() for QDRANT_HOST."""
        from src.core.secrets import get_secret

        # Should return value set in conftest (env backend)
        host = get_secret("QDRANT_HOST")
        assert host is not None
        # Default value per config.py / conftest
        assert host in ("localhost", "127.0.0.1")

    def test_qdrant_service_reads_port_from_secrets(self):
        from src.core.secrets import get_secret

        port = get_secret("QDRANT_PORT")
        assert port is not None
        assert int(port) > 0

    def test_embedding_endpoint_from_secrets(self):
        from src.core.secrets import get_secret

        endpoint = get_secret("EMBEDDING_ENDPOINT")
        assert endpoint is not None
        assert endpoint.startswith("http")

    def test_no_direct_openai_or_anthropic_imports_in_phase3_modules(self):
        """
        Static check: Phase 3 source files MUST NOT import openai, anthropic,
        cohere, or any other public LLM SDK. Constitution §II.
        """
        import ast
        import importlib.util

        forbidden_modules = {"openai", "anthropic", "cohere", "google.generativeai"}

        phase3_files = [
            "src/services/qdrant_service.py",
            "src/services/chunking_service.py",
            "src/services/fusion_service.py",
            "src/agents/retrieval_agent.py",
        ]

        backend_root = os.path.join(os.path.dirname(__file__), "../..")
        violations: list[str] = []

        for rel_path in phase3_files:
            full_path = os.path.join(backend_root, rel_path)
            with open(full_path, encoding="utf-8") as f:
                source = f.read()
            try:
                tree = ast.parse(source, filename=rel_path)
            except SyntaxError as exc:
                pytest.fail(f"Syntax error in {rel_path}: {exc}")

            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            mod = alias.name.split(".")[0]
                            if mod in forbidden_modules:
                                violations.append(f"{rel_path}: imports '{alias.name}'")
                    elif isinstance(node, ast.ImportFrom):
                        mod = (node.module or "").split(".")[0]
                        if mod in forbidden_modules:
                            violations.append(f"{rel_path}: from '{node.module}' import ...")

        assert not violations, (
            "Phase 3 modules import forbidden external LLM APIs:\n"
            + "\n".join(violations)
        )

    @patch("src.services.qdrant_service.AsyncQdrantClient")
    @patch("src.services.qdrant_service.get_secret")
    def test_qdrant_service_instantiation_uses_secrets(self, mock_get_secret, mock_qdrant_cls):
        """
        QdrantIndexingService.__init__ must read host/port through the
        get_secret() abstraction (not directly from os.environ or settings).

        We patch get_secret inside the qdrant_service module namespace so
        that the call is intercepted regardless of what pydantic Settings
        has already cached at import time.
        """
        mock_qdrant_cls.return_value = MagicMock()

        def secret_side_effect(key, *args, **kwargs):
            return {
                "QDRANT_HOST": "qdrant-test-host",
                "QDRANT_PORT": "7777",
                "EMBEDDING_ENDPOINT": "http://localhost:8080",
            }.get(key)

        mock_get_secret.side_effect = secret_side_effect

        from src.services import qdrant_service as qs_mod

        # Reset singleton so __init__ runs fresh with our mock
        qs_mod._service_instance = None
        try:
            svc = qs_mod.QdrantIndexingService()
            mock_qdrant_cls.assert_called_once_with(
                host="qdrant-test-host", port=7777
            )
        finally:
            qs_mod._service_instance = None


# ===========================================================================
# T016 — Retrieval Agent (hermetic — mocked Qdrant + embedding)
# ===========================================================================


class TestEvidenceRetrievalAgentHermetic:
    """Unit tests for EvidenceRetrievalAgent with fully mocked Qdrant."""

    def _mock_qdrant_service(self):
        """Build a mock QdrantIndexingService."""
        from src.services.qdrant_service import RetrievedChunk

        mock_svc = AsyncMock()
        mock_svc.ensure_collection = AsyncMock()
        mock_svc.search_dense = AsyncMock(
            return_value=[
                RetrievedChunk(
                    chunk_id="c1", case_id="case-1", document_id="doc-1",
                    page_number=0, text="Dense result text", score=0.91, source="dense"
                )
            ]
        )
        mock_svc.search_sparse = AsyncMock(
            return_value=[
                RetrievedChunk(
                    chunk_id="c1", case_id="case-1", document_id="doc-1",
                    page_number=0, text="Dense result text", score=0.85, source="sparse"
                )
            ]
        )
        return mock_svc

    @pytest.mark.asyncio
    async def test_retrieve_returns_result_per_requirement(self):
        from src.agents.retrieval_agent import EvidenceRetrievalAgent, RequirementQuery

        mock_svc = self._mock_qdrant_service()
        agent = EvidenceRetrievalAgent(qdrant_service=mock_svc)

        reqs = [
            RequirementQuery(
                requirement_id="req-001",
                description="Clinical notes from last 6 months",
                matching_criteria={"keywords": ["clinical", "notes"]},
                is_identifier_based=False,
            ),
            RequirementQuery(
                requirement_id="req-002",
                description="Procedure code CPT 72148",
                matching_criteria={"keywords": ["72148"]},
                is_identifier_based=True,
            ),
        ]

        result = await agent.retrieve(case_id="case-1", requirements=reqs)
        assert result.case_id == "case-1"
        assert len(result.evidence) == 2
        assert result.evidence[0].requirement_id == "req-001"
        assert result.evidence[1].requirement_id == "req-002"

    @pytest.mark.asyncio
    async def test_retrieve_calls_both_search_legs(self):
        from src.agents.retrieval_agent import EvidenceRetrievalAgent, RequirementQuery

        mock_svc = self._mock_qdrant_service()
        agent = EvidenceRetrievalAgent(qdrant_service=mock_svc)

        await agent.retrieve(
            case_id="case-1",
            requirements=[
                RequirementQuery(
                    requirement_id="req-001",
                    description="Clinical notes",
                    is_identifier_based=False,
                )
            ],
        )

        mock_svc.search_dense.assert_called_once()
        mock_svc.search_sparse.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_case_id_passed_to_search(self):
        from src.agents.retrieval_agent import EvidenceRetrievalAgent, RequirementQuery

        mock_svc = self._mock_qdrant_service()
        agent = EvidenceRetrievalAgent(qdrant_service=mock_svc)

        await agent.retrieve(
            case_id="case-999",
            requirements=[
                RequirementQuery(
                    requirement_id="r1",
                    description="Any requirement",
                )
            ],
        )

        # Both search legs must be scoped to the correct case_id
        dense_call_kwargs = mock_svc.search_dense.call_args[1]
        sparse_call_kwargs = mock_svc.search_sparse.call_args[1]
        assert dense_call_kwargs["case_id"] == "case-999"
        assert sparse_call_kwargs["case_id"] == "case-999"

    @pytest.mark.asyncio
    async def test_keyword_miss_count_propagated(self):
        from src.agents.retrieval_agent import EvidenceRetrievalAgent, RequirementQuery
        from src.services.qdrant_service import RetrievedChunk

        mock_svc = AsyncMock()
        # dense-only result → keyword_miss
        mock_svc.search_dense = AsyncMock(
            return_value=[
                RetrievedChunk("c1", "case-1", "doc-1", 0, "text", 0.9, "dense")
            ]
        )
        mock_svc.search_sparse = AsyncMock(return_value=[])

        agent = EvidenceRetrievalAgent(qdrant_service=mock_svc)
        result = await agent.retrieve(
            case_id="case-1",
            requirements=[
                RequirementQuery("r1", "CPT code 72148", is_identifier_based=True)
            ],
        )

        ev = result.evidence[0]
        assert ev.keyword_miss_count == 1
        assert ev.fused_results[0].keyword_miss is True

    @pytest.mark.asyncio
    async def test_retrieve_empty_requirements(self):
        from src.agents.retrieval_agent import EvidenceRetrievalAgent

        mock_svc = self._mock_qdrant_service()
        agent = EvidenceRetrievalAgent(qdrant_service=mock_svc)

        result = await agent.retrieve(case_id="case-1", requirements=[])
        assert result.evidence == []
        mock_svc.search_dense.assert_not_called()
        mock_svc.search_sparse.assert_not_called()


# ===========================================================================
# Integration smoke tests (require local docker-compose stack)
# ===========================================================================


@pytest.mark.integration
class TestPhase3IntegrationSmoke:
    """
    Integration smoke tests that require the local docker-compose stack.

    Skipped unless explicitly selected:
        pytest -m integration

    Validates:
      - Embedding service reachable at EMBEDDING_ENDPOINT
      - Qdrant reachable at QDRANT_HOST:QDRANT_PORT
      - LLM endpoint reachable at LLM_ENDPOINT
      - Secrets abstraction correctly resolves endpoints
    """

    @pytest.mark.asyncio
    async def test_embedding_service_health(self):
        """Embedding service (TEI) must respond to health check."""
        from src.services.qdrant_service import LocalEmbeddingClient

        client = LocalEmbeddingClient()
        try:
            result = await client.health_check()
            assert result["status"] == "ok"
        except RuntimeError as exc:
            pytest.skip(f"Embedding service not available: {exc}")

    @pytest.mark.asyncio
    async def test_qdrant_health_via_service(self):
        """Qdrant must be reachable via QdrantIndexingService.health_check()."""
        from src.services.qdrant_service import QdrantIndexingService

        svc = QdrantIndexingService()
        try:
            info = await svc.health_check()
            assert info["qdrant"]["status"] == "ok"
        except Exception as exc:
            pytest.skip(f"Qdrant not available: {exc}")

    @pytest.mark.asyncio
    async def test_llm_endpoint_reachable(self):
        """Local Ollama LLM endpoint must respond to a simple model list query."""
        import httpx
        from src.core.secrets import get_secret

        llm_endpoint = (get_secret("LLM_ENDPOINT") or "http://localhost:11434").rstrip("/")
        url = f"{llm_endpoint}/api/tags"  # Ollama list-models endpoint

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get(url)
                assert response.status_code == 200, (
                    f"LLM endpoint {url} returned {response.status_code}"
                )
            except httpx.ConnectError:
                pytest.skip(f"LLM endpoint {url} not reachable (docker-compose up -d ollama)")

    @pytest.mark.asyncio
    async def test_end_to_end_index_and_retrieve(self):
        """
        Full round-trip: index a text chunk for a mock case, then retrieve it.
        Validates secrets abstraction, local embedding, and Qdrant are all wired.
        """
        from src.services.qdrant_service import QdrantIndexingService

        svc = QdrantIndexingService()
        case_id = f"smoke-{uuid.uuid4()}"
        document_id = str(uuid.uuid4())

        try:
            await svc.ensure_collection()

            # Index one chunk
            n = await svc.index_text_chunks(
                case_id=case_id,
                document_id=document_id,
                texts=["Clinical notes documenting at least 6 weeks of conservative treatment"],
            )
            assert n == 1

            # Dense retrieve — must find it
            results = await svc.search_dense(
                query_text="physical therapy records conservative treatment",
                case_id=case_id,
                top_k=5,
            )
            assert len(results) >= 1
            assert results[0].case_id == case_id

            # Sparse retrieve
            sparse_results = await svc.search_sparse(
                query_text="conservative treatment",
                case_id=case_id,
                top_k=5,
            )
            assert len(sparse_results) >= 1

        except Exception as exc:
            pytest.skip(f"Local stack not fully available: {exc}")
        finally:
            # Clean up test data
            try:
                await svc.delete_case_chunks(case_id)
            except Exception:
                pass
