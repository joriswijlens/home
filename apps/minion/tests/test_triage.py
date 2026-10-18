from minion.flows import registry
from minion.flows.triage import build_prompt, verdict


def test_triage_is_registered():
    assert registry()["triage"].max_rounds == 40


def test_the_prompt_carries_repo_error_and_dry_run():
    prompt = build_prompt({
        "repo": "smartworkx/depot", "workdir": "/w", "error": "  NPE at X  \n", "dry_run": "true",
    })
    assert "Repository: smartworkx/depot" in prompt
    assert "THIS IS A DRY RUN." in prompt
    assert "```\nNPE at X\n```" in prompt


def test_a_wet_run_says_nothing_about_dry():
    assert "DRY RUN" not in build_prompt({"repo": "r", "workdir": "/w", "error": "e"})


def test_the_verdict_is_the_last_json_line():
    text = 'Created #12 and a branch.\n\n{"outcome": "fix_proposed", "issue": "u", "branch": "fix/12-npe"}\n'
    assert verdict(text) == {"outcome": "fix_proposed", "issue": "u", "branch": "fix/12-npe"}


def test_no_verdict_when_the_model_forgot():
    assert verdict("I did things, trust me.") is None
    assert verdict("{not json}") is None
