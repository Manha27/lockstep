import argparse
import json
from pathlib import Path

import yaml
from .core import (capture_baseline, first_failure, load_tutorial, run_tutorial)


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


def cmd_check(a):
    """Verification + evaluation. The clean app must pass N times; every
    mutation must be caught at the right step with the right diagnosis (or be
    correctly ignored)."""
    tut = load_tutorial(a.tutorial)
    exp = yaml.safe_load(Path(a.expectations).read_text(encoding="utf-8"))["mutations"]
    capture_baseline(tut, a.url)  # always start from a fresh baseline

    clean_fail = sum(1 for _ in range(a.repeat)
                     if first_failure(run_tutorial(tut, a.url, None)))
    print(f"\nClean app: {a.repeat - clean_fail}/{a.repeat} runs passed "
          f"(false alarms: {clean_fail})\n")

    head = f"{'mutation':<20}{'step (exp/got)':<30}{'diagnosis (exp/got)':<42}result"
    print(head)
    print("-" * len(head))
    rows, step_ok, diag_ok, detected, should_detect = [], 0, 0, 0, 0
    for name, want in exp.items():
        f = first_failure(run_tutorial(tut, a.url, name))
        want_step = want["step"] if want else None
        want_diag = want["diagnosis"] if want else None
        got_step = f["id"] if f else None
        got_diag = f["diagnosis"]["label"] if f else None
        s_ok, d_ok = got_step == want_step, got_diag == want_diag
        step_ok += s_ok
        diag_ok += d_ok
        if want:
            should_detect += 1
            detected += bool(f)
        rows.append({"mutation": name, "want_step": want_step, "got_step": got_step,
                     "want_diagnosis": want_diag, "got_diagnosis": got_diag,
                     "confidence": f["diagnosis"]["confidence"] if f else None,
                     "step_correct": s_ok, "diagnosis_correct": d_ok})
        print(f"{name:<20}{f'{want_step} / {got_step}':<30}"
              f"{f'{want_diag} / {got_diag}':<42}{'OK' if s_ok and d_ok else 'WRONG'}")

    n = len(exp)
    print(f"\nDetected:               {detected}/{should_detect} broken tutorials")
    print(f"False alarms (clean):   {clean_fail}/{a.repeat} runs")
    print(f"Right step identified:  {step_ok}/{n}")
    print(f"Right diagnosis:        {diag_ok}/{n}")
    Path("out").mkdir(exist_ok=True)
    Path("out/check.json").write_text(json.dumps(
        {"clean_runs": a.repeat, "clean_failures": clean_fail, "mutations": rows}, indent=2))


def main():
    p = argparse.ArgumentParser(prog="lockstep")
    p.add_argument("--url", default="http://localhost:5000")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("baseline"); b.add_argument("tutorial"); b.set_defaults(fn=cmd_baseline)

    r = sub.add_parser("run"); r.add_argument("tutorial")
    r.add_argument("--mutation"); r.add_argument("--repeat", type=int, default=1)
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("check"); c.add_argument("tutorial")
    c.add_argument("--expectations", default="tutorials/expectations.yaml")
    c.add_argument("--repeat", type=int, default=10); c.set_defaults(fn=cmd_check)

    a = p.parse_args()
    a.fn(a)


main()
