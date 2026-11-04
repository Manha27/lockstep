import pytest
from lockstep.core import load_tutorial


def test_loads_example_tutorial():
    t = load_tutorial("tutorials/export_report.yaml")
    assert [s["id"] for s in t["steps"]] == ["open_dashboard", "open_reports", "export"]


def test_rejects_click_without_target(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("steps:\n  - id: a\n    action: click\n")
    with pytest.raises(ValueError):
        load_tutorial(bad)
