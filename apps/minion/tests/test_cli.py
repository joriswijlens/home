"""`minion run`: one flow on one input, printed."""

import json

import pytest

from minion.cli import build_context, parse_args


def test_pairs_become_context(tmp_path):
    args = parse_args(["plan", "title=Fix it", "ref=7", "--workdir", str(tmp_path)])
    context = build_context(args)
    assert context["title"] == "Fix it"
    assert context["ref"] == "7"
    assert context["workdir"] == str(tmp_path)


def test_a_value_can_come_from_a_file(tmp_path):
    line = tmp_path / "error.log"
    line.write_text('{"log.level":"ERROR","message":"boom"}')
    args = parse_args(["plan", f"body=@{line}"])
    assert build_context(args)["body"] == line.read_text()


def test_a_context_file_is_the_base_and_pairs_override(tmp_path):
    base = tmp_path / "ctx.json"
    base.write_text(json.dumps({"title": "from file", "ref": "1"}))
    args = parse_args(["plan", "--context", str(base), "ref=2"])
    context = build_context(args)
    assert context["title"] == "from file"
    assert context["ref"] == "2"


def test_a_pair_without_equals_is_refused():
    with pytest.raises(SystemExit):
        build_context(parse_args(["plan", "nonsense"]))


def test_an_agent_directory_can_be_named(tmp_path):
    args = parse_args(["triage", "--agent", str(tmp_path), "repo=x"])
    assert args.agent == tmp_path
