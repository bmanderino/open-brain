import main

MISSING = "00000000-0000-4000-8000-000000000000"


def get(client, entry_id):
    entries = client.get("/entries?limit=100").json()["entries"]
    return next(e for e in entries if e["id"] == entry_id)


def test_patch_tags_only_changes_tags(client, add, ollama):
    e = add("keep me", project="p", tags=["a"])
    calls = (ollama.embed_calls, ollama.extract_calls)
    r = client.patch(f"/entries/{e['id']}", json={"tags": ["b", "c"]})
    assert r.status_code == 200
    assert r.json()["tags"] == ["b", "c"] and r.json()["project"] == "p"
    assert (ollama.embed_calls, ollama.extract_calls) == calls


def test_patch_project_set_and_clear(client, add):
    e = add("x", project="p")
    assert client.patch(f"/entries/{e['id']}", json={"project": ""}).json()["project"] is None
    point = main.qdrant.retrieve(main.COLLECTION, [e["id"]])[0]
    assert "project" not in point.payload
    assert client.patch(f"/entries/{e['id']}", json={"project": "q"}).json()["project"] == "q"
    assert client.patch(f"/entries/{e['id']}", json={"project": None}).json()["project"] is None


def test_patch_omitted_project_untouched(client, add):
    e = add("x", project="p")
    assert client.patch(f"/entries/{e['id']}", json={"tags": ["t"]}).json()["project"] == "p"


def test_patch_content_reembeds_and_reextracts(client, add, ollama):
    e = add("we use unittest")
    before = main.qdrant.retrieve(main.COLLECTION, [e["id"]], with_vectors=True)[0].vector
    r = client.patch(f"/entries/{e['id']}", json={"content": "we switched to pytest"})
    assert r.json()["content"] == "we switched to pytest"
    after = main.qdrant.retrieve(main.COLLECTION, [e["id"]], with_vectors=True)[0].vector
    assert after != before
    assert ollama.extract_calls == 2
    assert r.json()["created_at"] == e["created_at"] and r.json()["id"] == e["id"]
    top = client.post("/search", json={"query": "pytest switched"}).json()["results"][0]
    assert top["id"] == e["id"]


def test_patch_same_content_does_not_reembed(client, add, ollama):
    e = add("same")
    calls = ollama.embed_calls
    client.patch(f"/entries/{e['id']}", json={"content": "same"})
    assert ollama.embed_calls == calls


def test_patch_reextract_repairs_failed_metadata(client, add, ollama):
    ollama.extract_fails = True
    e = add("needs metadata")
    assert e["metadata_status"] == "failed"
    ollama.extract_fails = False
    calls = ollama.embed_calls
    r = client.patch(f"/entries/{e['id']}", json={"reextract": True}).json()
    assert r["metadata_status"] == "ok" and r["type"] == "decision"
    assert ollama.embed_calls == calls  # vector untouched


def test_patch_empty_content_rejected(client, add):
    e = add("x")
    assert client.patch(f"/entries/{e['id']}", json={"content": " "}).status_code == 400
    assert get(client, e["id"])["content"] == "x"


def test_patch_missing_and_malformed_ids(client):
    assert client.patch(f"/entries/{MISSING}", json={}).status_code == 404
    assert client.patch("/entries/not-a-uuid", json={}).status_code == 422


def test_delete(client, add):
    e = add("bye")
    assert client.delete(f"/entries/{e['id']}").json() == {"deleted": e["id"]}
    assert client.get("/entries").json()["count"] == 0
    assert client.delete(f"/entries/{e['id']}").status_code == 404


def test_delete_missing_and_malformed(client):
    assert client.delete(f"/entries/{MISSING}").status_code == 404
    assert client.delete("/entries/not-a-uuid").status_code == 422
