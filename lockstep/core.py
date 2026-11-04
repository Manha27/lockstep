"""LockStep core: load a tutorial, capture a baseline, replay it, report which
step broke. Elements are found by accessibility role + exact accessible name,
never CSS selectors, and a step passes only if the action works AND the
expected outcome is true."""
import json
import time
import urllib.request
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

STEP_TIMEOUT_MS = 2000
VIEWPORT = {"width": 1280, "height": 800}
ACTIONS = {"goto", "click", "fill"}


# ---------- loading ----------
def load_tutorial(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    for step in data["steps"]:
        if "id" not in step or step.get("action") not in ACTIONS:
            raise ValueError(f"Bad step: {step}")
        if step["action"] in ("click", "fill"):
            t = step.get("target") or {}
            if "role" not in t or "name" not in t:
                raise ValueError(f"Step {step['id']} needs target role + name")
    return data


def set_mutation(base_url, name):
    """Tell the demo app which mutation to apply ('reset' = clean app)."""
    req = urllib.request.Request(f"{base_url}/__mutate/{name or 'reset'}", method="POST")
    urllib.request.urlopen(req, timeout=5).read()


# ---------- helpers ----------
class StepFailure(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def locate(page, target):
    return page.get_by_role(target["role"], name=target["name"], exact=True)


def check_expectation(page, expect):
    if not expect:
        return
    try:
        if "url_contains" in expect:
            page.wait_for_url(lambda u: expect["url_contains"] in u, timeout=STEP_TIMEOUT_MS)
        if "text_visible" in expect:
            page.get_by_text(expect["text_visible"]).first.wait_for(
                state="visible", timeout=STEP_TIMEOUT_MS)
        if "element_visible" in expect:
            locate(page, expect["element_visible"]).wait_for(
                state="visible", timeout=STEP_TIMEOUT_MS)
    except PWTimeout:
        raise StepFailure("outcome_not_met")


def do_step(page, step, base_url):
    action = step["action"]
    if action == "goto":
        page.goto(base_url + step["url"])
    else:
        loc = locate(page, step["target"])
        try:
            loc.wait_for(state="visible", timeout=STEP_TIMEOUT_MS)
        except PWTimeout:
            raise StepFailure("target_not_found_or_hidden")
        try:
            if action == "click":
                loc.click(timeout=STEP_TIMEOUT_MS)
            else:
                loc.fill(step["value"], timeout=STEP_TIMEOUT_MS)
        except PWTimeout:
            raise StepFailure("target_not_clickable")
    check_expectation(page, step.get("expect"))


def new_page(p, headless=True):
    browser = p.chromium.launch(headless=headless)
    ctx = browser.new_context(viewport=VIEWPORT, reduced_motion="reduce")
    return browser, ctx.new_page()


# ---------- baseline ----------
def capture_baseline(tutorial, base_url, out_dir="out/baseline"):
    """Run the tutorial on the CLEAN app and save evidence for every step."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    set_mutation(base_url, None)
    record = {}
    with sync_playwright() as p:
        browser, page = new_page(p)
        for step in tutorial["steps"]:
            entry = {"intent": step.get("intent")}
            if step["action"] != "goto":
                loc = locate(page, step["target"])
                loc.wait_for(state="visible", timeout=STEP_TIMEOUT_MS)
                entry["bbox"] = loc.bounding_box()
            page.screenshot(path=str(out / f"{step['id']}_before.png"))
            do_step(page, step, base_url)
            page.screenshot(path=str(out / f"{step['id']}_after.png"))
            try:
                entry["aria"] = page.locator("body").aria_snapshot()
            except Exception:
                entry["aria"] = None
            record[step["id"]] = entry
        browser.close()
    (out / "baseline.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


# ---------- replay ----------
def run_tutorial(tutorial, base_url, mutation=None, out_dir="out/run"):
    """Replay all steps. Returns a list of per-step result dicts."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    set_mutation(base_url, mutation)
    results, failed = [], False
    with sync_playwright() as p:
        browser, page = new_page(p)
        for step in tutorial["steps"]:
            res = {"id": step["id"], "status": "SKIPPED", "reason": None, "seconds": 0.0}
            if not failed:
                t0 = time.time()
                try:
                    do_step(page, step, base_url)
                    res["status"] = "PASS"
                except StepFailure as e:
                    failed = True
                    res["status"], res["reason"] = "FAIL", e.reason
                    shot = out / f"{step['id']}_{mutation or 'clean'}_FAIL.png"
                    page.screenshot(path=str(shot))
                    res["screenshot"] = str(shot)
                res["seconds"] = round(time.time() - t0, 2)
            results.append(res)
        browser.close()
    set_mutation(base_url, None)
    return results


def first_failure(results):
    return next((r for r in results if r["status"] == "FAIL"), None)
