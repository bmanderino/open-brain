def search(client, query, **body):
    r = client.post("/search", json={"query": query, **body})
    assert r.status_code == 200, r.text
    return r.json()["results"]


def test_semantic_ranks_related_text_first(client, add):
    add("we deploy with docker compose")
    add("pytest is our test runner")
    top = search(client, "docker compose deploy")[0]
    assert top["content"] == "we deploy with docker compose"


def test_empty_query_rejected(client):
    assert client.post("/search", json={"query": " "}).status_code == 400


def test_limit_validated(client):
    assert client.post("/search", json={"query": "x", "limit": 0}).status_code == 422
    assert client.post("/search", json={"query": "x", "limit": 101}).status_code == 422


def test_bad_timestamp_rejected(client):
    assert client.post("/search", json={"query": "x", "created_after": "soon"}).status_code == 422


def test_project_scoping(client, add):
    add("the shared build step", project="foo")
    add("the shared build step notes", project="bar")
    add("the shared build step general")
    got = {r["content"] for r in search(client, "shared build step", project="foo")}
    assert got == {"the shared build step", "the shared build step general"}
    only = search(client, "shared build step", project="foo", include_unscoped=False)
    assert [r["content"] for r in only] == ["the shared build step"]


def test_filters_apply_to_search(client, add):
    add("alpha note", tags=["x"], source="mcp")
    add("alpha memo", tags=["y"], source="cli")
    assert [r["content"] for r in search(client, "alpha", tag="x")] == ["alpha note"]
    assert [r["content"] for r in search(client, "alpha", source_filter="cli")] == ["alpha memo"]
    assert len(search(client, "alpha", type="decision")) == 2
    assert search(client, "alpha", type="meeting") == []


def test_result_shape(client, add):
    add("shape check", project="p", tags=["t"])
    r = search(client, "shape check")[0]
    assert r["project"] == "p" and r["tags"] == ["t"]
    assert r["match"] in {"semantic", "keyword", "both"}
    assert set(r["metadata"]) == {"type", "topics", "people", "action_items"}


def test_hybrid_surfaces_exact_term_missed_by_vectors(client, add):
    # Six entries are vector-closer to the query; the one holding the rare token is not.
    for i in range(6):
        add(f"error handling notes variant {i} about errors", force=True)
    target = "zzq9 plus lots of other unrelated words filling this entry out"
    add(target)
    query = "error handling notes about errors zzq9"
    semantic = search(client, query, mode="semantic", limit=6)
    hybrid = search(client, query, limit=6)
    assert target not in [r["content"] for r in semantic]
    found = [r for r in hybrid if r["content"] == target]
    assert found and found[0]["match"] in ("keyword", "both")


def test_semantic_mode_reports_semantic_match(client, add):
    add("some text")
    assert {r["match"] for r in search(client, "some text", mode="semantic")} == {"semantic"}


def test_score_is_cosine_in_both_modes(client, add):
    add("relay failure code")
    hybrid = search(client, "relay failure code")[0]
    semantic = search(client, "relay failure code", mode="semantic")[0]
    assert abs(hybrid["score"] - semantic["score"]) < 1e-6


def test_stopword_only_query_still_works(client, add):
    add("the and of")
    assert len(search(client, "the and of")) == 1


def test_keyword_search_respects_project_filter(client, add):
    add("secrettoken lives here", project="a")
    add("secrettoken lives there", project="b")
    got = search(client, "secrettoken", project="a", include_unscoped=False)
    assert [r["content"] for r in got] == ["secrettoken lives here"]
