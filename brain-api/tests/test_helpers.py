from conftest import fake_embed

import main


def test_metadata_drops_placeholder_values():
    m = main.Metadata(people=["none", "N/A", " Dana "], action_items="None", topics=["", "x"])
    assert m.people == ["Dana"]
    assert m.action_items == []
    assert m.topics == ["x"]


def test_metadata_drops_placeholder_phrases():
    m = main.Metadata(
        people=["None mentioned", "no one", "Not applicable", "NONE.", "Dana"],
        action_items=["No action items", "Not specified", "none identified"],
        topics=["No topics", "not available", "qdrant"],
    )
    assert m.people == ["Dana"]
    assert m.action_items == []
    assert m.topics == ["qdrant"]


def test_metadata_keeps_values_that_merely_start_like_placeholders():
    names = ["Nonetheless Inc", "Nilsson", "Nil Smith", "Nora", "Notable changes", "Nobody Corp"]
    assert main.Metadata(people=names).people == names


def test_metadata_wraps_bare_string_and_coerces_type():
    m = main.Metadata(topics="infra", type="nonsense")
    assert m.topics == ["infra"]
    assert m.type == "other"


def test_tokenize_matches_index_rules():
    assert main.tokenize("Error E4417: relay-7 a 1.11.3") == ["error", "e4417", "relay", "11"]


def test_cosine():
    assert main.cosine([1, 0], [1, 0]) == 1.0
    assert main.cosine([1, 0], [0, 1]) == 0.0
    assert main.cosine([0, 0], [1, 1]) == 0.0


class Hit:
    def __init__(self, id, score=0.0, vector=None):
        self.id, self.score, self.vector = id, score, vector


def test_fuse_orders_by_rank_and_labels_sources():
    q = fake_embed("alpha")
    vec = [Hit("a", 0.9), Hit("b", 0.5)]
    kw = [Hit("b", vector=fake_embed("alpha")), Hit("c", vector=fake_embed("alpha beta"))]
    out = main.fuse(vec, kw, q, limit=10)
    assert [(p.id, m) for p, _, m in out] == [("b", "both"), ("a", "semantic"), ("c", "keyword")]
    scores = {p.id: s for p, s, _ in out}
    assert scores["a"] == 0.9  # vector hits keep their own cosine
    assert scores["b"] == 0.5
    assert scores["c"] == main.cosine(q, fake_embed("alpha beta"))  # keyword-only gets computed cosine
    assert 0 < scores["c"] < 1


def test_fuse_respects_limit():
    vec = [Hit(str(i), 1 - i / 10) for i in range(5)]
    assert len(main.fuse(vec, [], fake_embed("x"), limit=2)) == 2


def test_build_filter_empty_is_none():
    assert main.build_filter() is None
