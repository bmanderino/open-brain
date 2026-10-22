import json

from test_entries import seed

import main


def export(client):
    return [json.loads(ln) for ln in client.get("/export").text.splitlines() if ln]


def ids(entries):
    return [e["content"] for e in entries]


# Pinning

def test_ingest_pinned_is_stored_and_returned(client, add):
    data = add("always use pnpm", pinned=True)
    assert data["pinned"] is True
    assert client.get("/entries").json()["entries"][0]["pinned"] is True


def test_default_is_unpinned_and_stores_no_key(client, add):
    data = add("plain note")
    assert data["pinned"] is False
    point = main.qdrant.retrieve(main.COLLECTION, [data["id"]], with_payload=True)[0]
    assert "pinned" not in point.payload


def test_patch_pin_and_unpin(client, add):
    entry_id = add("note")["id"]
    assert client.patch(f"/entries/{entry_id}", json={"pinned": True}).json()["pinned"] is True
    assert client.patch(f"/entries/{entry_id}", json={"pinned": False}).json()["pinned"] is False
    point = main.qdrant.retrieve(main.COLLECTION, [entry_id], with_payload=True)[0]
    assert "pinned" not in point.payload


def test_patch_omitted_or_null_pinned_untouched(client, add):
    entry_id = add("note", pinned=True)["id"]
    assert client.patch(f"/entries/{entry_id}", json={"tags": ["x"]}).json()["pinned"] is True
    assert client.patch(f"/entries/{entry_id}", json={"pinned": None}).json()["pinned"] is True


def test_entries_pinned_filter(client, add):
    add("pinned one", pinned=True)
    add("loose one")
    got = client.get("/entries?pinned=true").json()["entries"]
    assert ids(got) == ["pinned one"]


def test_search_results_show_pinned(client, add):
    add("use pnpm everywhere", pinned=True)
    (hit,) = client.post("/search", json={"query": "pnpm"}).json()["results"]
    assert hit["pinned"] is True


def test_duplicate_response_reports_pinned(client, add):
    add("use pnpm everywhere", pinned=True)
    dup = add("use pnpm everywhere")
    assert dup["duplicate_of"] and dup["pinned"] is True


def test_pinned_survives_export_and_import(client, add):
    add("keep me", pinned=True, project="p")
    add("not me")
    original = sorted(export(client), key=lambda rec: rec["id"])
    assert [rec["pinned"] for rec in sorted(original, key=lambda r: r["content"])] == [True, False]
    for rec in original:
        client.delete(f"/entries/{rec['id']}")
    body = "\n".join(json.dumps(rec) for rec in original)
    assert client.post("/import", content=body).json()["imported"] == 2
    assert sorted(export(client), key=lambda rec: rec["id"]) == original


def test_import_without_pinned_key_means_unpinned(client):
    line = json.dumps({"content": "old export line"})
    client.post("/import", content=line)
    assert export(client)[0]["pinned"] is False


# /context

def context(client, **params):
    resp = client.get("/context", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_context_pinned_first_then_recent_without_repeats(client):
    seed(client, 6)
    client.patch("/entries/00000000-0000-4000-8000-000000000001", json={"pinned": True})
    data = context(client, recent=3)
    assert ids(data["pinned"]) == ["entry number 1"]
    assert ids(data["recent"]) == ["entry number 5", "entry number 4", "entry number 3"]
    assert data["pinned_total"] == 1


def test_context_recent_skips_pinned_even_when_newest(client):
    seed(client, 4)
    client.patch("/entries/00000000-0000-4000-8000-000000000003", json={"pinned": True})
    data = context(client, recent=2)
    assert ids(data["recent"]) == ["entry number 2", "entry number 1"]


def test_context_project_includes_unscoped_but_not_other_projects(client, add):
    add("mine", project="a", pinned=True)
    add("global pin", pinned=True)
    add("theirs", project="b", pinned=True)
    data = context(client, project="a")
    assert sorted(ids(data["pinned"])) == ["global pin", "mine"]


def test_context_without_project_is_unscoped_only(client, add):
    add("mine", project="a", pinned=True)
    add("global pin", pinned=True)
    add("project note", project="a")
    add("general note")
    data = context(client)
    assert ids(data["pinned"]) == ["global pin"]
    assert ids(data["recent"]) == ["general note"]


def test_context_caps_pinned_and_reports_total(client):
    seed(client, 5, pinned=True)
    data = context(client, max_pinned=2, recent=0)
    assert ids(data["pinned"]) == ["entry number 4", "entry number 3"]
    assert data["pinned_total"] == 5
    assert data["recent"] == []


def test_context_recent_zero_and_empty_brain(client):
    assert context(client, recent=0) == {
        "project": None, "pinned": [], "pinned_total": 0, "recent": [],
    }


def test_context_validates_params(client):
    assert client.get("/context?recent=-1").status_code == 422
    assert client.get("/context?recent=51").status_code == 422
    assert client.get("/context?max_pinned=101").status_code == 422
    assert client.get("/context?format=xml").status_code == 422


def test_context_text_is_compact_and_tells_claude_how_to_save(client, add):
    add("Use pnpm, not npm", project="web", pinned=True)
    add("Chose Vite over webpack\n\nfor build speed", project="web")
    resp = client.get("/context", params={"project": "web", "format": "text"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    text = resp.text
    assert text.startswith('Open Brain context for project "web":')
    assert text.index("Pinned:") < text.index("Use pnpm") < text.index("Recent:")
    assert "Chose Vite over webpack for build speed" in text  # whitespace collapsed to one line
    assert 'add_to_brain with project="web"' in text


def test_context_text_truncates_long_entries_and_notes_hidden_pins(client, add):
    add("older pin", pinned=True)
    add("x" * 1000, pinned=True)
    text = client.get("/context", params={"format": "text", "max_pinned": 1, "recent": 0}).text
    assert "x" * main.CONTEXT_MAX_CHARS not in text and "…" in text
    assert "(1 more pinned not shown" in text


def test_context_text_empty_brain(client):
    text = client.get("/context", params={"format": "text"}).text
    assert "Nothing stored yet." in text
