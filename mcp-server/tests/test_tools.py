ID = "3a8c7928-b658-4bde-92ee-6e02e5be5002"


def result(**over):
    base = {
        "id": ID,
        "content": "Use pytest",
        "source": "mcp",
        "tags": [],
        "project": None,
        "created_at": "2026-10-22T10:00:00+00:00",
        "score": 0.8123,
        "match": "semantic",
        "metadata": {"type": "other", "topics": [], "people": [], "action_items": []},
    }
    base.update(over)
    return base


def entry(**over):
    base = {
        "id": ID,
        "content": "Use pytest",
        "source": "mcp",
        "tags": [],
        "project": None,
        "created_at": "2026-10-22T10:00:00+00:00",
        "type": "other",
        "topics": [],
        "people": [],
        "action_items": [],
        "metadata_status": "ok",
    }
    base.update(over)
    return base


# Registration

def test_all_tools_registered_with_descriptions(run, tools):
    listed = run(tools.mcp.list_tools())
    names = {t.name: t for t in listed}
    assert set(names) == {
        "search_brain", "add_to_brain", "update_brain_entry", "list_brain", "brain_stats",
    }
    # Claude reads these descriptions to decide how to call the tools
    assert "project" in names["search_brain"].description
    assert "project" in names["add_to_brain"].description
    assert "force" in names["add_to_brain"].description
    assert "entry_id" in names["update_brain_entry"].description


def test_no_delete_tool(run, tools):
    assert not [t.name for t in run(tools.mcp.list_tools()) if "delete" in t.name]


# search_brain

def test_search_sends_only_query_and_limit_by_default(run, tools, api):
    api.reply("POST", "/search", body={"results": []})
    run(tools.search_brain("hello"))
    assert api.last_json() == {"query": "hello", "limit": 5}


def test_search_passes_filters_and_maps_source(run, tools, api):
    api.reply("POST", "/search", body={"results": []})
    run(tools.search_brain("q", limit=3, project="p", type="decision", tag="t", source="cli"))
    assert api.last_json() == {
        "query": "q", "limit": 3, "project": "p", "type": "decision", "tag": "t",
        "source_filter": "cli",
    }


def test_search_no_results_message(run, tools, api):
    api.reply("POST", "/search", body={"results": []})
    assert run(tools.search_brain("nothing")) == "No results found for: 'nothing'"


def test_search_formats_results(run, tools, api):
    api.reply("POST", "/search", body={"results": [result(
        project="open-brain", tags=["a", "b"],
        metadata={"type": "decision", "topics": ["x"], "people": ["Dana"], "action_items": ["ship"]},
    )]})
    out = run(tools.search_brain("q"))
    assert f"[{ID}]" in out  # id is shown so update_brain_entry can use it
    assert "score: 0.812" in out
    assert "2026-10-22" in out
    assert "project: open-brain" in out
    assert "[a, b]" in out
    assert "Use pytest" in out
    assert "type: decision" in out and "topics: x" in out
    assert "people: Dana" in out and "actions: ship" in out


def test_search_labels_exact_term_matches_only(run, tools, api):
    api.reply("POST", "/search", body={"results": [
        result(id="a", match="semantic"), result(id="b", match="keyword"), result(id="c", match="both"),
    ]})
    out = run(tools.search_brain("q"))
    lines = [ln for ln in out.splitlines() if ln.startswith(("1.", "2.", "3."))]
    assert "exact-term" not in lines[0]
    assert "exact-term match" in lines[1] and "exact-term match" in lines[2]


def test_search_hides_type_other_and_empty_fields(run, tools, api):
    api.reply("POST", "/search", body={"results": [result()]})
    out = run(tools.search_brain("q"))
    assert "type:" not in out and "topics:" not in out and "people:" not in out


def test_search_api_error(run, tools, api):
    api.reply("POST", "/search", status=502, body="Ollama down")
    assert run(tools.search_brain("q")) == "Error searching brain: Ollama down"


# add_to_brain

def test_add_sends_defaults(run, tools, api):
    api.reply("POST", "/ingest", body={"id": ID, "metadata": {}})
    run(tools.add_to_brain("note"))
    assert api.last_json() == {
        "content": "note", "tags": [], "source": "mcp", "project": None, "force": False,
    }


def test_add_passes_project_tags_force(run, tools, api):
    api.reply("POST", "/ingest", body={"id": ID, "metadata": {}})
    run(tools.add_to_brain("note", tags=["t"], project="p", force=True))
    body = api.last_json()
    assert body["tags"] == ["t"] and body["project"] == "p" and body["force"] is True


def test_add_success_output(run, tools, api):
    api.reply("POST", "/ingest", body={
        "id": ID, "project": "p",
        "metadata": {"type": "decision", "topics": ["x"], "people": ["Dana"], "action_items": ["ship"]},
        "metadata_status": "ok",
    })
    out = run(tools.add_to_brain("note", tags=["t"], project="p"))
    assert f"Stored in brain (id: {ID})" in out
    assert '"note"' in out and "Tags: t" in out and "Project: p" in out
    assert "Type: decision" in out and "Topics: x" in out
    assert "People: Dana" in out and "Action items: ship" in out
    assert "failed" not in out


def test_add_reports_duplicate_as_not_stored(run, tools, api):
    api.reply("POST", "/ingest", body={
        "id": ID, "content": "existing text", "duplicate_of": ID, "duplicate_score": 0.9712,
        "metadata": {},
    })
    out = run(tools.add_to_brain("existing text again"))
    assert out.startswith("Not stored")
    assert ID in out and "0.971" in out and "existing text" in out
    assert "force=True" in out
    assert "Stored in brain" not in out


def test_add_flags_failed_metadata(run, tools, api):
    api.reply("POST", "/ingest", body={"id": ID, "metadata": {}, "metadata_status": "failed"})
    out = run(tools.add_to_brain("note"))
    assert "Stored in brain" in out
    assert "metadata extraction failed" in out


def test_add_api_error(run, tools, api):
    api.reply("POST", "/ingest", status=400, body="Content cannot be empty")
    assert run(tools.add_to_brain(" ")) == "Error storing in brain: Content cannot be empty"


def test_add_does_not_share_tags_between_calls(run, tools, api):
    api.reply("POST", "/ingest", body={"id": ID, "metadata": {}})
    run(tools.add_to_brain("one", tags=None))
    run(tools.add_to_brain("two"))
    assert api.last_json()["tags"] == []


# update_brain_entry

def test_update_sends_only_given_fields(run, tools, api):
    api.reply("PATCH", f"/entries/{ID}", body=entry())
    run(tools.update_brain_entry(ID, tags=["x"]))
    assert api.last_json() == {"reextract": False, "tags": ["x"]}


def test_update_empty_project_is_sent_to_clear_it(run, tools, api):
    api.reply("PATCH", f"/entries/{ID}", body=entry())
    run(tools.update_brain_entry(ID, project=""))
    assert api.last_json()["project"] == ""


def test_update_empty_tags_list_clears_tags(run, tools, api):
    api.reply("PATCH", f"/entries/{ID}", body=entry())
    run(tools.update_brain_entry(ID, tags=[]))
    assert api.last_json()["tags"] == []


def test_update_content_and_reextract(run, tools, api):
    api.reply("PATCH", f"/entries/{ID}", body=entry())
    run(tools.update_brain_entry(ID, content="new", reextract=True))
    assert api.last_json() == {"reextract": True, "content": "new"}


def test_update_output(run, tools, api):
    api.reply("PATCH", f"/entries/{ID}", body=entry(
        content="new text", project="p", tags=["t"], type="decision", topics=["x"],
        people=["Dana"], action_items=["ship"],
    ))
    out = run(tools.update_brain_entry(ID, content="new text"))
    assert f"Updated entry {ID}" in out and '"new text"' in out
    assert "Project: p" in out and "Tags: t" in out and "Type: decision" in out
    assert "People: Dana" in out and "Action items: ship" in out


def test_update_not_found(run, tools, api):
    api.reply("PATCH", f"/entries/{ID}", status=404, body={"detail": "Entry not found"})
    assert run(tools.update_brain_entry(ID, tags=["x"])) == f"No entry with id {ID}"


def test_update_other_error(run, tools, api):
    api.reply("PATCH", f"/entries/{ID}", status=400, body="Content cannot be empty")
    assert run(tools.update_brain_entry(ID, content=" ")).startswith("Error updating entry:")


def test_update_flags_failed_metadata(run, tools, api):
    api.reply("PATCH", f"/entries/{ID}", body=entry(metadata_status="failed"))
    assert "reextract=True" in run(tools.update_brain_entry(ID, reextract=True))


# list_brain

def test_list_default_params(run, tools, api):
    api.reply("GET", "/entries", body={"entries": []})
    run(tools.list_brain())
    assert api.last_params() == {"limit": "10"}


def test_list_passes_filters(run, tools, api):
    api.reply("GET", "/entries", body={"entries": []})
    run(tools.list_brain(limit=3, project="p", type="idea", tag="t"))
    assert api.last_params() == {"limit": "3", "project": "p", "type": "idea", "tag": "t"}


def test_list_empty_message(run, tools, api):
    api.reply("GET", "/entries", body={"entries": []})
    assert run(tools.list_brain()) == "Your brain is empty. Add something with add_to_brain!"


def test_list_output_includes_ids_and_project(run, tools, api):
    api.reply("GET", "/entries", body={"entries": [
        entry(project="p", tags=["t"], type="decision", topics=["x"], people=["Dana"]),
    ]})
    out = run(tools.list_brain())
    assert out.startswith("Recent brain entries:")
    assert f"[{ID}]" in out and "project: p" in out and "[t]" in out
    assert "type: decision" in out and "topics: x" in out and "people: Dana" in out


def test_list_api_error(run, tools, api):
    api.reply("GET", "/entries", status=500, body="boom")
    assert run(tools.list_brain()) == "Error listing brain: boom"


# brain_stats

def test_stats_output(run, tools, api):
    api.reply("GET", "/stats", body={
        "total": 3, "by_source": {"cli": 1, "mcp": 2},
        "top_topics": [{"topic": "qdrant", "count": 2}],
        "top_people": [{"person": "Dana", "count": 1}],
    })
    out = run(tools.brain_stats())
    assert "3 total entries" in out
    assert out.index("mcp: 2") < out.index("cli: 1")  # sorted by count, descending
    assert "qdrant: 2" in out and "Dana: 1" in out


def test_stats_empty_brain(run, tools, api):
    api.reply("GET", "/stats", body={"total": 0, "by_source": {}, "top_topics": [], "top_people": []})
    assert run(tools.brain_stats()).strip() == "Brain Stats — 0 total entries"


def test_stats_api_error(run, tools, api):
    api.reply("GET", "/stats", status=500, body="boom")
    assert run(tools.brain_stats()) == "Error fetching brain stats: boom"
