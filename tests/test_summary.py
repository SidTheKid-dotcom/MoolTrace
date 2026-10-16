from mooltrace.summary import format_summary


def test_summary_warn_eoc_is_three_lines():
    text = format_summary(
        {
            "decision": "warn",
            "exit_code": 2,
            "notices_checked_ago": "2 h ago",
            "reasons": [
                {
                    "code": "expression_of_concern",
                    "notice_doi": "10.2337/dc25-ec09",
                    "notice_date": "2025-08-20",
                    "root_doi": "10.2337/diacare.26.12.3215",
                    "steps": [
                        {
                            "url": "https://www.healthline.com/nutrition/cinnamon-and-diabetes",
                            "title": None,
                            "doi": None,
                        },
                        {
                            "title": "Cinnamon: A Systematic Review",
                            "year": 2022,
                            "doi": "10.3390/nu14132773",
                        },
                        {
                            "title": "Khan cinnamon trial",
                            "year": 2003,
                            "doi": "10.2337/diacare.26.12.3215",
                        },
                    ],
                }
            ],
        }
    )
    lines = [line for line in text.strip().splitlines() if line]
    assert lines[0].startswith("WARN (exit 2)")
    assert "Expression of Concern" in lines[0]
    assert "healthline.com/nutrition/cinnamon-and-diabetes" in lines[1]
    assert "10.2337/dc25-ec09" in text
    assert "mooltrace rewrite" in text


def test_summary_names_sppaths_strength():
    text = format_summary(
        {
            "decision": "warn",
            "exit_code": 2,
            "algorithm": {
                "name": "algo.SPpaths",
                "strength": 0.72,
                "explanation": "Decided by: algo.SPpaths, path strength 0.72",
            },
            "reasons": [
                {
                    "code": "expression_of_concern",
                    "notice_doi": "10.2337/dc25-ec09",
                    "steps": [{"url": "https://www.healthline.com/nutrition/cinnamon-and-diabetes"}],
                }
            ],
        }
    )
    assert "Decided by: algo.SPpaths, path strength 0.72" in text


def test_summary_block_and_pass():
    blocked = format_summary(
        {
            "decision": "block",
            "exit_code": 1,
            "reasons": [{"code": "retraction", "notice_doi": "10.1/r", "steps": []}],
        }
    )
    assert blocked.startswith("BLOCK (exit 1)")
    passed = format_summary({"decision": "pass", "exit_code": 0, "reasons": []})
    assert passed.startswith("PASS (exit 0)")
    assert "not a medical-accuracy check" in passed
