def test_query_returns_stub_answer_when_corpus_empty(client):
    response = client.post("/query", json={"query": "what is grounding precision?"})
    assert response.status_code == 200
    body = response.json()
    # No corpus wired up yet in this scaffold -> no chunks -> graceful no-context answer.
    assert body["answer"] == "No relevant context was found for this query."
    assert body["citations"] == []
    assert body["strategy_used"] == "hybrid"  # default fallback, no classifier configured
    assert body["fell_back_to_hybrid"] is True
    assert body["latency_seconds"] < 5.0  # Success Criterion 2 sanity check


def test_query_forced_strategy_is_respected(client):
    response = client.post(
        "/query",
        json={"query": "test", "forced_strategy": "vector"},
    )
    assert response.status_code == 200
    assert response.json()["strategy_used"] == "vector"


def test_query_rejects_empty_string(client):
    response = client.post("/query", json={"query": ""})
    assert response.status_code == 422
