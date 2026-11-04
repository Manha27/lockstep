from lockstep.report import summarize, to_markdown


def case(name, want, got, secs=1.0):
    return {"mutation": name, "seconds": secs,
            "expected": {"step": "s", "diagnosis": want} if want else None,
            "got": {"step": "s", "diagnosis": got, "confidence": 0.9} if got else None}


def test_summary_counts_detection_misses_and_false_alarms():
    cases = [
        case("a", "MOVED", "MOVED"),
        case("b", "RENAMED", "REMOVED"),      # detected, wrong diagnosis
        case("c", "REMOVED", None),           # missed entirely
        case("d", None, None),                # harmless, correctly ignored
        case("e", None, "REMOVED"),           # harmless, wrongly flagged
    ]
    s = summarize(cases, clean_runs=10, clean_failures=0)
    assert s["broken_cases"] == 3 and s["detected"] == 2 and s["missed"] == 1
    assert s["harmless_cases"] == 2 and s["harmless_false_alarms"] == 1
    assert s["diagnosis_correct"] == 2  # a and d


def test_markdown_lists_known_misses():
    cases = [case("b", "RENAMED", "REMOVED")]
    md = to_markdown(summarize(cases, 10, 0), cases, "demo")
    assert "Known misses" in md and "**b**" in md
