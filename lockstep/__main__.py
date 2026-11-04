import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import yaml
from .core import (capture_baseline, first_failure, load_tutorial, run_tutorial)
from .report import summarize, to_markdown
from .screen import build_screen


def cmd_baseline(a):
    rec = capture_baseline(load_tutorial(a.tutorial), a.url)
    print(f"Baseline saved for {len(rec)} steps in out/baseline/")


def cmd_run(a):
    tut = load_tutorial(a.tutorial)
    exit_code = 0
    for i in range(a.repeat):
        results = run_tutorial(tut, a.url, a.mutation)
        for r in results:
            extra = ""
            if r["diagnosis"]:
                d = r["diagnosis"]
                extra = f"  -> {d['label']} ({d['confidence']})  {d['evidence']}"
            print(f"[{i + 1}] {r['id']:<16} {r['status']:<8} {r['seconds']}s{extra}")
        if first_failure(results):
            exit_code = 1
    raise SystemExit(exit_code)


def cmd_eval(a):
    """Full evaluation. The clean app must pass N times; every mutation must be
    caught at the right step with the right diagnosis (or correctly ignored).
    Writes out/results.json and out/results.md."""
    tut = load_tutorial(a.tutorial)
    exp = yaml.safe_load(Path(a.expectations).read_text(encoding="utf-8"))["mutations"]
    capture_baseline(tut, a.url)  # always start from a fresh baseline

    clean_fail = sum(1 for _ in range(a.repeat)
                     if first_failure(run_tutorial(tut, a.url, None)))
    print(f"\nClean app: {a.repeat - clean_fail}/{a.repeat} runs passed "
          f"(false alarms: {clean_fail})\n")

    head = f"{'mutation':<22}{'expected':<22}{'got':<22}{'conf':<7}result"
    print(head)
    print("-" * len(head))
    cases = []
    for name, want in exp.items():
        t0 = time.time()
        f = first_failure(run_tutorial(tut, a.url, name))
        seconds = round(time.time() - t0, 2)
        got = None
        if f:
            d = f["diagnosis"]
            got = {"step": f["id"], "diagnosis": d["label"], "confidence": d["confidence"],
                   "reason": f["reason"], "evidence": d["evidence"]}
        case = {"mutation": name, "expected": want, "got": got, "seconds": seconds,
                "baseline_screenshot": f.get("baseline_screenshot") if f else None,
                "failure_screenshot": f.get("screenshot") if f else None,
                "baseline_bbox": f.get("baseline_bbox") if f else None}
        cases.append(case)
        w = want["diagnosis"] if want else "no failure"
        g = got["diagnosis"] if got else "no failure"
        step_ok = (want["step"] if want else None) == (got["step"] if got else None)
        ok = "OK" if step_ok and w == g else "MISS"
        print(f"{name:<22}{w:<22}{g:<22}{str(got['confidence'] if got else '-'):<7}{ok}")

    summary = summarize(cases, a.repeat, clean_fail)
    out = Path("out")
    out.mkdir(exist_ok=True)
    (out / "results.json").write_text(json.dumps({
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tutorial": tut.get("name"), "app_url": a.url,
        "summary": summary, "cases": cases}, indent=2), encoding="utf-8")
    (out / "results.md").write_text(to_markdown(summary, cases, tut.get("name")),
                                    encoding="utf-8")
    s = summary
    print(f"\nDetected:                 {s['detected']}/{s['broken_cases']} broken tutorials")
    print(f"False alarms (clean app): {s['clean_false_alarms']}/{s['clean_runs']} runs")
    print(f"False alarms (harmless):  {s['harmless_false_alarms']}/{s['harmless_cases']}")
    print(f"Right step identified:    {s['step_correct']}/{s['mutations_total']}")
    print(f"Right diagnosis:          {s['diagnosis_correct']}/{s['mutations_total']}")
    print("\nSaved out/results.json and out/results.md")


def cmd_screen(a):
    out = build_screen(a.tutorial)
    print(f"Saved {out}")
    if a.open:
        import webbrowser
        webbrowser.open(Path(out).resolve().as_uri())


def main():
    p = argparse.ArgumentParser(prog="lockstep")
    p.add_argument("--url", default="http://localhost:5000")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("baseline"); b.add_argument("tutorial"); b.set_defaults(fn=cmd_baseline)

    r = sub.add_parser("run"); r.add_argument("tutorial")
    r.add_argument("--mutation"); r.add_argument("--repeat", type=int, default=1)
    r.set_defaults(fn=cmd_run)

    for name in ("eval", "check"):  # "check" kept as an alias from M1/M2
        c = sub.add_parser(name); c.add_argument("tutorial")
        c.add_argument("--expectations", default="tutorials/expectations.yaml")
        c.add_argument("--repeat", type=int, default=10); c.set_defaults(fn=cmd_eval)

    sc = sub.add_parser("screen"); sc.add_argument("tutorial")
    sc.add_argument("--open", action="store_true"); sc.set_defaults(fn=cmd_screen)

    a = p.parse_args()
    a.fn(a)


main()
