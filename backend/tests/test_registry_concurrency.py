from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.ingest.registry import DocumentRegistry


def test_job_numbers_are_unique_under_concurrent_reservation(tmp_path: Path) -> None:
    registry = DocumentRegistry(tmp_path / "r.sqlite3")
    with ThreadPoolExecutor(max_workers=8) as pool:
        numbers = list(pool.map(lambda _: registry.reserve_job_number(), range(40)))
    assert sorted(numbers) == list(range(1, 41))


def test_reservation_continues_after_existing_jobs_and_never_reuses(tmp_path: Path) -> None:
    registry = DocumentRegistry(tmp_path / "r.sqlite3")
    assert registry.reserve_job_number() == 1
    assert registry.reserve_job_number() == 2
    reopened = DocumentRegistry(tmp_path / "r.sqlite3")  # counter persists across restarts
    assert reopened.reserve_job_number() == 3
