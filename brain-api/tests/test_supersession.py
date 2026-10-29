import json

import main

OLD = "7b1d2c3e-0000-4000-8000-000000000001"


def supersede(client, old_id, new_id):
    return client.patch(f"/entries/{old_id}", json={"superseded_by": new_id})


def pair(add):
    old = add("we use postgres for storage", project="p")["id"]
    new = add("we use sqlite for storage now", project="p", force=True)["id"]
    return old, new


def search(client, **body):
    return client.post("/search", json={"query": "storage", **body}).json()["results"]


def test_superseded_entry_is_hidden_everywhere_by_default(client, add):
    old, new = pair(add)
    resp = supersede(client, old, new)
    assert resp.status_code == 200 and resp.json()["superseded_by"] == new
    assert [r["id"] for r in search(client)] == [new]
    assert [r["id"] for r in search(client, mode="semantic")] == [new]
    assert [e["id"] for e in client.get("/entries").json()["entries"]] == [new]
    ctx = client.get("/context?project=p").json()
    assert [e["id"] for e in ctx["recent"]] == [new]


def test_superseded_pins_leave_context(client, add):
    old = add("always use postgres", pinned=True)["id"]
    new = add("always use sqlite", pinned=True, force=True)["id"]
    supersede(client, old, new)
    ctx = client.get("/context").json()
    assert [e["id"] for e in ctx["pinned"]] == [new] and ctx["pinned_total"] == 1


def test_include_superseded_shows_them_marked(client, add):
    old, new = pair(add)
    supersede(client, old, new)
    hits = {r["id"]: r for r in search(client, include_superseded=True)}
    assert set(hits) == {old, new}
    assert hits[old]["superseded_by"] == new and hits[new]["superseded_by"] is None
    listed = client.get("/entries?include_superseded=true").json()["entries"]
    assert {e["id"] for e in listed} == {old, new}


def test_restore_with_null_or_empty(client, add):
    old, new = pair(add)
    for value in ("", None):
        supersede(client, old, new)
        assert (
            client.patch(f"/entries/{old}", json={"superseded_by": value}).json()["superseded_by"]
            is None
        )
        assert {r["id"] for r in search(client)} == {old, new}
    point = main.qdrant.retrieve(main.COLLECTION, [old], with_payload=True)[0]
    assert "superseded_by" not in point.payload


def test_omitted_field_leaves_supersession_alone(client, add):
    old, new = pair(add)
    supersede(client, old, new)
    assert client.patch(f"/entries/{old}", json={"tags": ["x"]}).json()["superseded_by"] == new


def test_rejects_bad_targets(client, add):
    old, new = pair(add)
    assert supersede(client, old, old).status_code == 422
    assert supersede(client, old, "nope").status_code == 422
    assert supersede(client, old, OLD).status_code == 422  # no such entry
    assert supersede(client, OLD, new).status_code == 404  # the entry being edited is missing


def test_rejects_cycles(client, add):
    a, b = pair(add)
    c = add("third storage note", project="p", force=True)["id"]
    supersede(client, a, b)
    supersede(client, b, c)
    assert supersede(client, c, a).status_code == 422  # c -> a -> b -> c
    assert supersede(client, b, a).status_code == 422


def test_deleting_the_replacement_restores_the_old_entry(client, add):
    old, new = pair(add)
    supersede(client, old, new)
    client.delete(f"/entries/{new}")
    assert [r["id"] for r in search(client)] == [old]
    assert client.get("/entries").json()["entries"][0]["superseded_by"] is None


def test_superseded_entries_do_not_block_dedup(client, add):
    old, new = pair(add)
    supersede(client, old, new)
    again = add("we use postgres for storage", project="p")
    assert again["duplicate_of"] is None and again["id"] not in (old, new)


def test_ingest_surfaces_neighbors_below_the_dedup_threshold(client, add, monkeypatch):
    monkeypatch.setattr(main, "NEIGHBOR_MIN_SCORE", 0.3)
    old = add("we use postgres for storage", project="p")
    resp = add("we use sqlite for storage", project="p")
    assert resp["duplicate_of"] is None
    (near,) = resp["possibly_supersedes"]
    assert near["id"] == old["id"] and near["content"] == old["content"]
    assert near["created_at"] == old["created_at"] and 0.3 <= near["score"] < main.DEDUP_THRESHOLD


def test_neighbors_respect_floor_scope_and_superseded(client, add, monkeypatch):
    monkeypatch.setattr(main, "NEIGHBOR_MIN_SCORE", 0.3)
    add("we use postgres for storage", project="other")
    stale = add("we use mysql for storage", project="p")["id"]
    assert add("we use sqlite for storage", project="p")["possibly_supersedes"][0]["id"] == stale
    supersede(client, stale, add("replacement", project="p")["id"])
    later = add("we use sqlite for storage again", project="p", force=True)["possibly_supersedes"]
    assert stale not in [n["id"] for n in later]
    monkeypatch.setattr(main, "NEIGHBOR_MIN_SCORE", 0.99)
    assert add("sqlite wins on storage", project="p", force=True)["possibly_supersedes"] == []


def test_force_still_returns_neighbors(client, add, monkeypatch):
    monkeypatch.setattr(main, "NEIGHBOR_MIN_SCORE", 0.3)
    add("we use postgres for storage")
    forced = add("we use postgres for storage", force=True)
    assert forced["duplicate_of"] is None and len(forced["possibly_supersedes"]) == 1


def test_superseded_survives_export_and_import(client, add):
    old, new = pair(add)
    supersede(client, old, new)
    original = sorted(
        (json.loads(ln) for ln in client.get("/export").text.splitlines() if ln),
        key=lambda rec: rec["id"],
    )
    assert {r["id"]: r["superseded_by"] for r in original} == {old: new, new: None}
    for rec in original:
        client.delete(f"/entries/{rec['id']}")
    body = "\n".join(json.dumps(rec) for rec in original)
    assert client.post("/import", content=body).json()["imported"] == 2
    again = sorted(
        (json.loads(ln) for ln in client.get("/export").text.splitlines() if ln),
        key=lambda rec: rec["id"],
    )
    assert again == original
