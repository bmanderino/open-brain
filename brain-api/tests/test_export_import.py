import json

import main

NEW_ID = "11111111-1111-4111-8111-111111111111"


def export(client):
    r = client.get("/export")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert "attachment" in r.headers["content-disposition"]
    return [json.loads(line) for line in r.text.splitlines()]


def do_import(client, lines, **params):
    body = "\n".join(ln if isinstance(ln, str) else json.dumps(ln) for ln in lines)
    r = client.post("/import", content=body, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_export_shape_and_no_vectors(client, add):
    add("one", project="p", tags=["t"])
    (line,) = export(client)
    assert set(line) == {
        "id",
        "content",
        "source",
        "tags",
        "project",
        "pinned",
        "superseded_by",
        "created_at",
        "metadata",
        "metadata_status",
    }
    assert line["metadata"]["type"] == "decision"


def test_export_empty(client):
    assert export(client) == []


def test_export_covers_more_than_one_batch(client, add):
    for i in range(130):
        add(f"entry {i} unique{i}", force=True)
    assert len(export(client)) == 130


def test_restore_is_faithful(client, add):
    add("alpha", project="p", tags=["a"])
    add("beta")
    original = sorted(export(client), key=lambda rec: rec["id"])
    for rec in original:
        client.delete(f"/entries/{rec['id']}")
    result = do_import(client, original)
    assert result == {"imported": 2, "skipped_existing": 0, "reextracted": 0, "failed": []}
    assert sorted(export(client), key=lambda rec: rec["id"]) == original


def test_reimport_skips_existing(client, add):
    add("alpha")
    lines = export(client)
    assert do_import(client, lines)["skipped_existing"] == 1
    assert client.get("/entries").json()["count"] == 1


def test_overwrite_replaces(client, add):
    add("alpha")
    (line,) = export(client)
    line["content"] = "changed"
    assert do_import(client, [line], overwrite="true")["imported"] == 1
    assert export(client)[0]["content"] == "changed"


def test_import_reembeds_every_entry(client, add, ollama):
    add("alpha")
    lines = export(client)
    client.delete(f"/entries/{lines[0]['id']}")
    calls = ollama.embed_calls
    do_import(client, lines)
    assert ollama.embed_calls == calls + 1


def test_good_metadata_reused_without_llm(client, ollama):
    line = {"content": "x", "metadata": {"type": "idea"}, "metadata_status": "ok"}
    r = do_import(client, [line])
    assert r["reextracted"] == 0 and ollama.extract_calls == 0
    assert export(client)[0]["metadata"]["type"] == "idea"


def test_missing_or_failed_metadata_is_extracted(client, ollama):
    lines = [
        {"content": "no metadata"},
        {"content": "failed one", "metadata": {"type": "idea"}, "metadata_status": "failed"},
    ]
    r = do_import(client, lines)
    assert r["imported"] == 2 and r["reextracted"] == 2 and ollama.extract_calls == 2
    assert {rec["metadata"]["type"] for rec in export(client)} == {"decision"}


def test_import_keeps_created_at_and_defaults_id(client):
    do_import(client, [{"content": "old", "created_at": "2020-01-02T03:04:05+00:00"}])
    (line,) = export(client)
    assert line["created_at"] == "2020-01-02T03:04:05+00:00"
    assert len(line["id"]) == 36


def test_import_skips_dedup_check(client):
    r = do_import(client, [{"id": NEW_ID, "content": "same text"}, {"content": "same text"}])
    assert r["imported"] == 2


def test_bad_lines_reported_not_fatal(client):
    lines = [
        {"content": "good one"},
        "not json",
        {"id": "bad", "content": "x"},
        {"content": "   "},
        {"content": "bad date", "created_at": "never"},
        {"id": NEW_ID, "content": "first"},
        {"id": NEW_ID, "content": "repeat id"},
        "",
        {"content": "good two"},
    ]
    r = do_import(client, lines)
    assert r["imported"] == 3
    assert [f["line"] for f in r["failed"]] == [2, 3, 4, 5, 7]
    assert "repeat id" not in {rec["content"] for rec in export(client)}


def test_embedding_failure_reported_per_line(client, ollama):
    ollama.embed_fails = True
    r = do_import(client, [{"content": "a"}, {"content": "b"}])
    assert r["imported"] == 0 and len(r["failed"]) == 2
    assert client.get("/entries").json()["count"] == 0


def test_import_cleans_placeholder_metadata(client):
    do_import(client, [{"content": "x", "metadata": {"people": ["none"]}, "metadata_status": "ok"}])
    assert export(client)[0]["metadata"]["people"] == []


def test_import_works_across_more_than_one_batch(client):
    lines = [{"content": f"entry {i} unique{i}"} for i in range(45)]
    assert do_import(client, lines)["imported"] == 45
    assert main.qdrant.count(main.COLLECTION).count == 45
