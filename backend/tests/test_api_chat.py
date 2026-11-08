"""API integration: upload with fakes, then chat over SSE with a mocked LLM."""

import json

from fastapi.testclient import TestClient

from app.llm.client import LLMError
from app.models import RouteDecision
from app.services import Services
from tests.fakes import FakeLLM


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def seed(client: TestClient, resume_text: str, job_text: str) -> dict[str, str]:
    ids = {}
    ids["resume"] = client.post("/documents", files={"file": ("cv.txt", resume_text.encode())},
                                data={"doc_type": "resume"}).json()["doc_id"]
    for n in (1, 2):
        ids[f"job{n}"] = client.post("/documents", files={"file": (f"j{n}.txt", job_text.encode())},
                                     data={"doc_type": "job"}).json()["doc_id"]
    return ids


def test_retrieve_for_job_two_only_touches_job_two_and_resume(client: TestClient, resume_text: str, job_text: str) -> None:
    ids = seed(client, resume_text, job_text)
    body = client.post("/chat/retrieve", json={"question": "What does Job #2 require?"}).json()
    assert body["route"]["method"] == "keyword"
    assert body["route"]["doc_ids"] == [ids["resume"], ids["job2"]]
    assert {s["chunk"]["doc_id"] for s in body["sources"]} == {ids["resume"], ids["job2"]}
    assert [s["n"] for s in body["sources"]] == list(range(1, len(body["sources"]) + 1))


def test_chat_streams_route_sources_tokens_done(client: TestClient, services: Services, resume_text: str, job_text: str) -> None:
    seed(client, resume_text, job_text)
    services.llm = FakeLLM(answer="You know Python [1].", route=RouteDecision(scope="all_jobs", job_numbers=[]))
    res = client.post("/chat", json={"question": "What skills am I missing?"})
    assert res.status_code == 200 and res.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(res.text)
    names = [e for e, _ in events]
    assert names[0] == "route" and names[1] == "sources" and names[-1] == "done"
    assert "".join(d["text"] for e, d in events if e == "token").strip() == "You know Python [1]."
    done = events[-1][1]
    assert done["citations"] == [1] and done["usage"]["output_tokens"] == 20
    # The prompt sent to the model contains the numbered chunks and the question.
    prompt = services.llm.calls[-1]["messages"][0]["content"]
    assert '<chunk n="1"' in prompt and "What skills am I missing?" in prompt


def test_chat_stream_error_event(client: TestClient, services: Services, resume_text: str, job_text: str) -> None:
    seed(client, resume_text, job_text)
    services.llm = FakeLLM(fail_stream=LLMError("rate limited", retryable=True))
    events = parse_sse(client.post("/chat", json={"question": "Which role fits me best?"}).text)
    assert events[-1] == ("error", {"detail": "rate limited", "retryable": True})


def test_chat_with_no_documents_still_answers(client: TestClient) -> None:
    events = parse_sse(client.post("/chat", json={"question": "Which role fits me best?"}).text)
    assert events[0][1]["method"] == "empty" and events[1][1]["sources"] == []


def test_chat_rejects_empty_question(client: TestClient) -> None:
    assert client.post("/chat", json={"question": ""}).status_code == 422
