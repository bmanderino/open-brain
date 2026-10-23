from test_supersession import supersede

MISSING = "7b1d2c3e-0000-4000-8000-000000000001"


def related(client, entry_id, **params):
    resp = client.get(f"/entries/{entry_id}/related", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()["related"]


def test_related_is_closest_first_and_excludes_itself(client, add):
    me = add("postgres storage setup guide")["id"]
    close = add("postgres storage setup notes", force=True)["id"]
    add("completely different words here", force=True)
    got = related(client, me)
    assert [n["id"] for n in got] == [close]
    assert got[0]["created_at"] and 0.5 <= got[0]["score"] <= 1
    assert me not in [n["id"] for n in got]


def test_related_threshold_and_limit(client, add):
    me = add("postgres storage setup guide")["id"]
    for i in range(4):
        add(f"postgres storage setup notes {i}", force=True)
    assert len(related(client, me, limit=2)) == 2
    assert related(client, me, min_score=1.0) == []
    assert len(related(client, me, min_score=0)) == 4


def test_related_scope_follows_entry_project(client, add):
    mine = add("postgres storage", project="p")["id"]
    same = add("postgres storage a", project="p", force=True)["id"]
    general = add("postgres storage b", force=True)["id"]
    add("postgres storage c", project="other", force=True)
    assert {n["id"] for n in related(client, mine)} == {same, general}
    # an unscoped entry sees only unscoped ones
    assert {n["id"] for n in related(client, general)} == set()


def test_related_hides_superseded_unless_asked(client, add):
    me = add("we use postgres for storage")["id"]
    old = add("postgres storage legacy", force=True)["id"]
    supersede(client, old, add("postgres storage newer", force=True)["id"])
    assert old not in [n["id"] for n in related(client, me)]
    assert old in [n["id"] for n in related(client, me, include_superseded="true")]


def test_related_errors(client):
    assert client.get(f"/entries/{MISSING}/related").status_code == 404
    assert client.get("/entries/nope/related").status_code == 422
    assert client.get(f"/entries/{MISSING}/related?limit=0").status_code == 422


def test_related_stores_nothing(client, add):
    me = add("we use postgres for storage")["id"]
    add("postgres storage setup", force=True)
    before = client.get("/export").text
    related(client, me)
    assert client.get("/export").text == before
