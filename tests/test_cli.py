from pathlib import Path


def test_check_alias_summary_and_json(monkeypatch, capsys):
    from mooltrace.__main__ import main

    payload = {
        "decision": "warn",
        "exit_code": 2,
        "summary": "A path reaches an Expression of Concern.",
        "notices_checked_ago": "just now",
        "reasons": [
            {
                "code": "expression_of_concern",
                "notice_doi": "10.2337/dc25-ec09",
                "notice_date": "2025-08-20",
                "steps": [{"url": "https://www.healthline.com/nutrition/cinnamon-and-diabetes"}],
            }
        ],
    }
    monkeypatch.setattr("mooltrace.__main__.check_answer", lambda *a, **k: payload)
    monkeypatch.setattr("mooltrace.__main__.sys.stdout.isatty", lambda: False)
    code = main(["check", "--url", "https://www.healthline.com/nutrition/cinnamon-and-diabetes", "--summary"])
    assert code == 2
    out = capsys.readouterr().out
    assert out.startswith("WARN (exit 2)")
    assert "{" not in out.splitlines()[0]

    code = main(["check-answer", "--json", "--text", "10.1016/j.jsps.2015.03.013"])
    assert code == 2
    dumped = capsys.readouterr().out
    assert '"decision": "warn"' in dumped


def test_check_help_documents_flags():
    from mooltrace.__main__ import main
    import pytest

    with pytest.raises(SystemExit) as exc:
        main(["check", "--help"])
    assert exc.value.code == 0


def test_recheck_affected_cli(monkeypatch, capsys):
    from mooltrace.__main__ import main

    monkeypatch.setattr(
        "mooltrace.__main__.recheck_affected",
        lambda doi, depth=2: {
            "query_doi": doi,
            "affected": 1,
            "summary": "This Expression of Concern affects 1 stored answer.",
            "rechecks": [{"decision": "warn", "exit_code": 2}],
        },
    )
    code = main(["recheck-affected", "10.2337/dc25-ec09"])
    assert code == 0
    assert "affects 1 stored answer" in capsys.readouterr().out


def test_help_covers_summary_and_check(tmp_path: Path, capsys):
    from mooltrace.__main__ import main
    import pytest

    with pytest.raises(SystemExit):
        main(["--help"])
    text = capsys.readouterr().out
    assert "check" in text
    assert "recheck-affected" in text
