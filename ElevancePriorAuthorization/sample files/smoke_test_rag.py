"""
scripts/smoke_test_rag.py

Manual smoke test for the Phase 3 fixes:
  1. Stable BM25 hashing across process restarts (the hash() -> md5 fix)
  2. Cross-page chunk overlap (the chunk_pages() carry-over fix)

This deliberately runs INDEXING and QUERYING as two SEPARATE process
invocations, because that's the only way to actually exercise the bug the
old hash() implementation had. Running both steps in one script (one Python
process) would use one PYTHONHASHSEED for both and could never expose the
issue — which is exactly why the original unit tests didn't catch it either.

Prerequisites:
  - docker compose up -d   (Qdrant + TEI must be reachable)
  - Run from the backend/ directory so `src.*` imports resolve, e.g.:
      cd backend
      python ../scripts/smoke_test_rag.py index
      python ../scripts/smoke_test_rag.py query

Usage:
  Step 1 (in one terminal / one process):
      python smoke_test_rag.py index

  Step 2 (in a NEW terminal, or just run again — each `python` invocation
  is a fresh process with a fresh random PYTHONHASHSEED by default):
      python smoke_test_rag.py query
"""
import asyncio
import sys
import uuid

sys.path.insert(0, ".")  # run from backend/

from src.services.chunking_service import chunk_pages
from src.services.qdrant_service import get_qdrant_service

# Fixed case_id so the `index` and `query` steps refer to the same data.
SMOKE_CASE_ID = "00000000-0000-0000-0000-0000000000aa"
SMOKE_DOC_ID = str(uuid.uuid4())

# Same two "pages" used in the automated regression test — the sentence
# deliberately continues across the page break.
PAGE_1 = (
    "Patient presents with a six week history of lower back pain radiating "
    "into the left leg, consistent with lumbar radiculopathy MBR-778241. "
    "Given the persistence of pain despite adequate conservative"
)
PAGE_2 = (
    "management, advanced imaging is recommended to rule out a structural "
    "cause such as disc herniation. Medical necessity for CPT 72148 is "
    "established given six weeks of conservative therapy."
)


async def do_index() -> None:
    service = get_qdrant_service()
    await service.ensure_collection()

    chunks = chunk_pages(
        pages=[PAGE_1, PAGE_2],
        case_id=SMOKE_CASE_ID,
        document_id=SMOKE_DOC_ID,
    )
    print(f"Chunked into {len(chunks)} chunk(s):")
    for c in chunks:
        preview = c.text[:80].replace("\n", " ")
        print(f"  page={c.page_number}  \"{preview}...\"")

    # Confirm the overlap fix: page 1's chunk content should reappear at the
    # START of page 2's chunk if overlap correctly crossed the page break.
    page0 = [c for c in chunks if c.page_number == 0]
    page1 = [c for c in chunks if c.page_number == 1]
    if page0 and page1 and "conservative" in page1[0].text[:60].lower():
        print("  ✓ Overlap check: page 2's chunk starts with carried-over "
              "text from page 1 (cross-page overlap fix confirmed).")
    else:
        print("  ⚠ Overlap check inconclusive — inspect the chunk text above.")

    texts = [c.text for c in chunks]
    pages = [c.page_number for c in chunks]
    n = await service.index_text_chunks(
        case_id=SMOKE_CASE_ID,
        document_id=SMOKE_DOC_ID,
        texts=texts,
        page_numbers=pages,
    )
    print(f"\nIndexed {n} chunk(s) into Qdrant under case_id={SMOKE_CASE_ID}.")
    print("Now run this script again with `query` — ideally in a fresh "
          "terminal/process — to confirm sparse search still finds them.")


async def do_query() -> None:
    service = get_qdrant_service()

    # This term ("CPT 72148" / "MBR-778241") only matters to EXACT/keyword
    # matching — dense search alone might still find it via semantic
    # similarity, so the meaningful check is the SPARSE leg specifically.
    for term in ["MBR-778241", "CPT 72148", "conservative therapy"]:
        results = await service.search_sparse(
            query_text=term,
            case_id=SMOKE_CASE_ID,
            top_k=5,
        )
        status = "✓ FOUND" if results else "✗ NOT FOUND"
        print(f"{status}  sparse search for {term!r} → {len(results)} hit(s)")
        for r in results[:2]:
            preview = r.text[:80].replace("\n", " ")
            print(f"           score={r.score:.4f}  \"{preview}...\"")

    print(
        "\nIf all three show FOUND, the stable-hash fix is confirmed: this "
        "query ran in a separate process from indexing, with a different "
        "PYTHONHASHSEED, and the sparse vectors still matched."
    )


async def do_cleanup() -> None:
    service = get_qdrant_service()
    await service.delete_case_chunks(SMOKE_CASE_ID)
    print(f"Deleted all smoke-test chunks for case_id={SMOKE_CASE_ID}.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("index", "query", "cleanup"):
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    if command == "index":
        asyncio.run(do_index())
    elif command == "query":
        asyncio.run(do_query())
    else:
        asyncio.run(do_cleanup())
