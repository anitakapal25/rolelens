from app.models import Chunk
from app.retrieval.search import number_chunks, retrieve, select_for_document
from app.retrieval.store import ScoredChunk
from tests.fakes import FakeEmbedder, InMemoryStore, fake_vector


def chunk(doc_id: str, i: int, doc_type: str = "job") -> Chunk:
    return Chunk(chunk_id=f"{doc_id}:{i}", doc_id=doc_id, doc_type=doc_type, doc_label=doc_id,  # type: ignore[arg-type]
                 section="requirements", index=i, text=f"{doc_id} text {i}")


def scored(doc_id: str, i: int, d: float) -> ScoredChunk:
    return ScoredChunk(chunk=chunk(doc_id, i), distance=d)


def filled_store() -> InMemoryStore:
    store = InMemoryStore()
    chunks = [chunk("resume", i, "resume") for i in range(3)] + \
             [chunk("j1", i) for i in range(10)] + [chunk("j2", i) for i in range(10)]
    store.upsert(chunks, [fake_vector(c.text) for c in chunks])
    return store


ORDER = {"resume": (0, 0), "j1": (1, 1), "j2": (1, 2)}


def test_filtered_search_never_returns_excluded_documents() -> None:
    result = retrieve("q", ["resume", "j2"], FakeEmbedder(), filled_store(), k_for=lambda _: 4, max_distance=2.0,
                      doc_order=ORDER.__getitem__)
    assert {r.chunk.doc_id for r in result} == {"resume", "j2"}


def test_top_k_is_per_document_so_resume_is_not_crowded_out() -> None:
    result = retrieve("q", ["j1", "resume", "j2"], FakeEmbedder(), filled_store(), k_for=lambda _: 3,
                      max_distance=2.0, doc_order=ORDER.__getitem__)
    per_doc = [r.chunk.doc_id for r in result]
    assert per_doc.count("resume") == 3 and per_doc.count("j1") == 3 and per_doc.count("j2") == 3


def test_k_can_differ_per_document() -> None:
    result = retrieve("q", ["resume", "j1"], FakeEmbedder(), filled_store(),
                      k_for=lambda d: 3 if d == "resume" else 1, max_distance=2.0, doc_order=ORDER.__getitem__)
    assert [r.chunk.doc_id for r in result] == ["resume", "resume", "resume", "j1"]


def test_documents_ordered_resume_first_and_numbered_from_one() -> None:
    result = retrieve("q", ["j2", "j1", "resume"], FakeEmbedder(), filled_store(), k_for=lambda _: 2, max_distance=2.0,
                      doc_order=ORDER.__getitem__)
    assert [r.chunk.doc_id for r in result] == ["resume", "resume", "j1", "j1", "j2", "j2"]
    assert [r.n for r in result] == [1, 2, 3, 4, 5, 6]


def test_no_documents_no_embedding_call() -> None:
    embedder = FakeEmbedder()
    assert retrieve("q", [], embedder, filled_store(), lambda _: 4, 0.8, ORDER.__getitem__) == []
    assert embedder.calls == []


def test_select_drops_far_chunks_but_keeps_best() -> None:
    hits = [scored("j", 1, 0.9), scored("j", 2, 0.5), scored("j", 3, 0.7), scored("j", 4, 0.95)]
    kept = select_for_document(hits, k=3, max_distance=0.8)
    assert [h.distance for h in kept] == [0.5, 0.7]
    only_far = select_for_document([scored("j", 1, 0.99)], k=3, max_distance=0.8)
    assert len(only_far) == 1  # a routed document is never silently missing


def test_number_chunks_flattens_in_order() -> None:
    numbered = number_chunks([[scored("a", 0, 0.1)], [], [scored("b", 0, 0.2), scored("b", 1, 0.3)]])
    assert [(r.n, r.chunk.doc_id) for r in numbered] == [(1, "a"), (2, "b"), (3, "b")]


def test_whole_document_keeps_far_chunks() -> None:
    hits = [scored("r", 1, 0.5), scored("r", 2, 0.95)]
    assert len(select_for_document(hits, k=10, max_distance=0.8)) == 1
    assert len(select_for_document(hits, k=10, max_distance=0.8, whole_document=True)) == 2
