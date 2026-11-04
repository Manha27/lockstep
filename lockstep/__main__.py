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
            extra = f"  ({r['reason']})" if r["reason"] else ""
            print(f"[{i + 1}] {r['id']:<16} {r['status']:<8} {r['seconds']}s{extra}")
        if first_failure(results):
            exit_code = 1
    raise SystemExit(exit_code)


def cmd_check(a):
    """M1 verification: clean app must pass N times; every mutation must be
    caught at the expected step (or correctly ignored)."""
    tut = load_tutorial(a.tutorial)
    exp = yaml.safe_load(Path(a.expectations).read_text(encoding="utf-8"))["mutations"]

    clean_fail = sum(1 for _ in range(a.repeat)
                     if first_failure(run_tutorial(tut, a.url, None)))
    print(f"\nClean app: {a.repeat - clean_fail}/{a.repeat} runs passed "
          f"(false alarms: {clean_fail})\n")

    print(f"{'mutation':<20}{'expected':<16}{'got':<16}{'reason':<28}result")
    print("-" * 84)
    ok = 0
    rows = []
    for name, expected in exp.items():
        f = first_failure(run_tutorial(tut, a.url, name))
        got = f["id"] if f else None
        good = got == expected
        ok += good
        rows.append({"mutation": name, "expected": expected, "got": got,
                     "reason": f["reason"] if f else None, "correct": good})
        print(f"{name:<20}{str(expected):<16}{str(got):<16}"
              f"{str(f['reason'] if f else '-'):<28}{'OK' if good else 'WRONG'}")
    print(f"\n{ok}/{len(exp)} mutations handled correctly")
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
