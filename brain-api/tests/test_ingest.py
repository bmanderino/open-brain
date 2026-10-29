import main


def test_ingest_response_and_defaults(client, add):
    e = add("remember this")
    assert e["source"] == "manual"
    assert e["tags"] == []
    assert e["project"] is None
    assert e["duplicate_of"] is None
    assert e["metadata"]["type"] == "decision"


def test_null_tags_normalized(client):
    r = client.post("/ingest", json={"content": "x", "tags": None})
    assert r.status_code == 200
    assert r.json()["tags"] == []


def test_blank_project_not_stored(client, add):
    e = add("x", project="   ")
    assert e["project"] is None
    point = main.qdrant.retrieve(main.COLLECTION, [e["id"]])[0]
    assert "project" not in point.payload


def test_empty_content_rejected(client):
    assert client.post("/ingest", json={"content": "  "}).status_code == 400


def test_embedding_failure_stores_nothing(client, ollama):
    ollama.embed_fails = True
    assert client.post("/ingest", json={"content": "x"}).status_code == 502
    assert client.get("/entries").json()["count"] == 0


def test_metadata_failure_is_flagged_but_stored(client, add, ollama):
    ollama.extract_fails = True
    e = add("some note")
    assert e["metadata_status"] == "failed"
    assert e["metadata"]["type"] == "other"
    assert client.get("/entries").json()["entries"][0]["metadata_status"] == "failed"


# Dedup


def test_exact_duplicate_returns_existing(client, add):
    first = add("use pytest for tests", project="p")
    again = add("use pytest for tests", project="p")
    assert again["duplicate_of"] == first["id"]
    assert again["id"] == first["id"]
    assert again["duplicate_score"] >= main.DEDUP_THRESHOLD
    assert client.get("/entries").json()["count"] == 1


def test_duplicate_check_is_per_project(client, add):
    add("use pytest for tests", project="a")
    other = add("use pytest for tests", project="b")
    unscoped = add("use pytest for tests")
    assert other["duplicate_of"] is None
    assert unscoped["duplicate_of"] is None
    assert client.get("/entries").json()["count"] == 3


def test_unscoped_duplicates_detected(client, add):
    first = add("tabs not spaces")
    assert add("tabs not spaces")["duplicate_of"] == first["id"]


def test_force_bypasses_dedup(client, add):
    add("same text")
    forced = add("same text", force=True)
    assert forced["duplicate_of"] is None
    assert client.get("/entries").json()["count"] == 2


def test_different_text_not_duplicate(client, add):
    add("use pytest for tests")
    assert add("deploy with docker compose")["duplicate_of"] is None


def test_dedup_threshold_can_be_disabled(client, add, monkeypatch):
    monkeypatch.setattr(main, "DEDUP_THRESHOLD", 2.0)
    add("same text")
    assert add("same text")["duplicate_of"] is None
