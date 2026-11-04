"""Turn raw evaluation cases into a summary dict and a markdown table.

A case looks like:
  {"mutation": str, "expected": {"step","diagnosis"} | None,
   "got": {"step","diagnosis","confidence","reason","evidence"} | None,
   "seconds": float, "baseline_screenshot": str|None, "failure_screenshot": str|None}
"""


def _step_ok(c):
    want = c["expected"]["step"] if c["expected"] else None
    got = c["got"]["step"] if c["got"] else None
    return want == got


def _diag_ok(c):
    want = c["expected"]["diagnosis"] if c["expected"] else None
    got = c["got"]["diagnosis"] if c["got"] else None
    return want == got


def summarize(cases, clean_runs, clean_failures):
    broken = [c for c in cases if c["expected"]]
    harmless = [c for c in cases if not c["expected"]]
    detected = sum(1 for c in broken if c["got"])
    flagged_harmless = sum(1 for c in harmless if c["got"])
    times = [c["seconds"] for c in cases]
    return {
        "mutations_total": len(cases),
        "broken_cases": len(broken),
        "harmless_cases": len(harmless),
        "detected": detected,
        "missed": len(broken) - detected,
        "clean_runs": clean_runs,
        "clean_false_alarms": clean_failures,
        "harmless_false_alarms": flagged_harmless,
        "step_correct": sum(_step_ok(c) for c in cases),
        "diagnosis_correct": sum(_diag_ok(c) for c in cases),
        "avg_seconds_per_run": round(sum(times) / len(times), 2) if times else 0.0,
    }


def to_markdown(summary, cases, tutorial_name):
    s = summary
    pct = lambda a, b: f"{100 * a / b:.0f}%" if b else "n/a"
    lines = [
        f"# LockStep evaluation: {tutorial_name}", "",
        "| Metric | Result |", "|---|---|",
        f"| Broken tutorials detected | {s['detected']}/{s['broken_cases']} ({pct(s['detected'], s['broken_cases'])}) |",
        f"| False alarms on the unchanged app | {s['clean_false_alarms']}/{s['clean_runs']} runs |",
        f"| False alarms on harmless changes | {s['harmless_false_alarms']}/{s['harmless_cases']} |",
        f"| Right failing step identified | {s['step_correct']}/{s['mutations_total']} ({pct(s['step_correct'], s['mutations_total'])}) |",
        f"| Right diagnosis | {s['diagnosis_correct']}/{s['mutations_total']} ({pct(s['diagnosis_correct'], s['mutations_total'])}) |",
        f"| Average time per replay | {s['avg_seconds_per_run']} s |",
        "", "## Per mutation", "",
        "| Mutation | Expected | Got | Confidence | Result |", "|---|---|---|---|---|",
    ]
    for c in cases:
        want = c["expected"]["diagnosis"] if c["expected"] else "no failure"
        got = c["got"]["diagnosis"] if c["got"] else "no failure"
        conf = c["got"]["confidence"] if c["got"] else "-"
        ok = "OK" if _step_ok(c) and _diag_ok(c) else "MISS"
        lines.append(f"| {c['mutation']} | {want} | {got} | {conf} | {ok} |")
    misses = [c for c in cases if not (_step_ok(c) and _diag_ok(c))]
    lines += ["", "## Known misses", ""]
    if misses:
        for c in misses:
            want = c["expected"]["diagnosis"] if c["expected"] else "no failure"
            got = c["got"]["diagnosis"] if c["got"] else "no failure"
            lines.append(f"- **{c['mutation']}**: expected {want}, got {got}.")
    else:
        lines.append("None in this set (the set is small and hand-built, so this is not a "
                     "claim about real products).")
    return "\n".join(lines) + "\n"
