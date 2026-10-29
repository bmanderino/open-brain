import json
from datetime import datetime, timedelta, timezone

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def seed(client, n, **fields):
    """Import n entries with controlled created_at (minute i after BASE), shuffled ids."""
    lines = [
        json.dumps(
            {
                "id": f"00000000-0000-4000-8000-{i:012d}",
                "content": f"entry number {i}",
                "created_at": (BASE + timedelta(minutes=i)).isoformat(),
                "metadata": {"type": "idea"},
                **fields,
            }
        )
        for i in range(n)
    ]
    r = client.post("/import", content="\n".join(reversed(lines)))
    assert r.json()["imported"] == n, r.text


def contents(resp):
    return [e["content"] for e in resp.json()["entries"]]


def test_newest_first_beyond_limit(client):
    seed(client, 55)
    got = contents(client.get("/entries?limit=10"))
    assert got == [f"entry number {i}" for i in range(54, 44, -1)]


def test_paging_with_next_before_covers_everything_once(client):
    seed(client, 55)
    seen, before = [], None
    while True:
        url = "/entries?limit=10" + (f"&before={before}" if before else "")
        data = client.get(url.replace("+", "%2B")).json()
        seen += [e["content"] for e in data["entries"]]
        before = data["next_before"]
        if before is None:
            break
    assert seen == [f"entry number {i}" for i in range(54, -1, -1)]


def test_next_before_null_when_page_not_full(client):
    seed(client, 3)
    assert client.get("/entries?limit=10").json()["next_before"] is None


def test_limit_validated(client):
    assert client.get("/entries?limit=0").status_code == 422
    assert client.get("/entries?limit=101").status_code == 422


def test_bad_timestamp_rejected(client):
    assert client.get("/entries?before=yesterday").status_code == 422
    assert client.get("/entries?after=nope").status_code == 422


def test_after_and_before_window(client):
    seed(client, 10)
    lo = (BASE + timedelta(minutes=2, seconds=30)).isoformat().replace("+", "%2B")
    hi = (BASE + timedelta(minutes=6, seconds=30)).isoformat().replace("+", "%2B")
    got = contents(client.get(f"/entries?after={lo}&before={hi}"))
    assert got == [f"entry number {i}" for i in (6, 5, 4, 3)]


# Filters


def test_project_filter_includes_unscoped_by_default(client, add):
    add("in foo", project="foo")
    add("in bar", project="bar")
    add("general")
    assert sorted(contents(client.get("/entries?project=foo"))) == ["general", "in foo"]


def test_project_filter_can_exclude_unscoped(client, add):
    add("in foo", project="foo")
    add("general")
    got = contents(client.get("/entries?project=foo&include_unscoped=false"))
    assert got == ["in foo"]


def test_type_tag_source_filters(client, add):
    add("a", tags=["x"], source="mcp")
    add("b", tags=["y"], source="cli")
    assert contents(client.get("/entries?tag=x")) == ["a"]
    assert contents(client.get("/entries?source=cli")) == ["b"]
    assert len(contents(client.get("/entries?type=decision"))) == 2
    assert contents(client.get("/entries?type=meeting")) == []


def test_filters_combine_with_and(client, add):
    add("a", project="foo", tags=["x"])
    add("b", project="foo", tags=["y"])
    assert contents(client.get("/entries?project=foo&include_unscoped=false&tag=x")) == ["a"]


def test_legacy_entries_without_new_fields_still_listed(client):
    from qdrant_client.models import PointStruct

    import main

    main.qdrant.upsert(
        main.COLLECTION,
        [
            PointStruct(
                id="00000000-0000-4000-8000-000000000001",
                vector=[0.1] * 64,
                payload={"content": "old entry", "created_at": BASE.isoformat()},
            )
        ],
    )
    e = client.get("/entries?project=foo").json()["entries"][0]
    assert e["content"] == "old entry"
    assert e["source"] == "unknown" and e["type"] == "other" and e["metadata_status"] is None
