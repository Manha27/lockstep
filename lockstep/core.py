"""LockStep core: load a tutorial, capture a baseline, replay it, and when a
step breaks say WHAT changed (diagnosis) with visual evidence.

Elements are found by accessibility role + exact accessible name, never CSS
selectors. A step passes only if the action works AND the expected outcome is
true."""
import json
import re
import time
import urllib.request
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

STEP_TIMEOUT_MS = 2000
VIEWPORT = {"width": 1280, "height": 800}
ACTIONS = {"goto", "click", "fill"}
BASELINE_PATH = "out/baseline/baseline.json"
RENAME_IOU = 0.4  # how much a same-role element must overlap the old position


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


def load_baseline(path=BASELINE_PATH):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def set_mutation(base_url, name):
    """Tell the demo app which mutation to apply ('reset' = clean app)."""
    req = urllib.request.Request(f"{base_url}/__mutate/{name or 'reset'}", method="POST")
    urllib.request.urlopen(req, timeout=5).read()


# ---------- geometry helpers ----------
def iou(a, b):
    """Intersection-over-union of two boxes {x, y, width, height}.
    1.0 = same place and size, 0.0 = no overlap."""
    x1, y1 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x2 = min(a["x"] + a["width"], b["x"] + b["width"])
    y2 = min(a["y"] + a["height"], b["y"] + b["height"])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union else 0.0


def controls(aria_text):
    """Pull (role, name) pairs for buttons and links out of an aria snapshot."""
    return set(re.findall(r'- (button|link) "([^"]+)"', aria_text or ""))


def outline(page, bbox):
    """Draw a red box where the element USED to be, so the screenshot shows
    exactly what changed."""
    if not bbox:
        return
    page.evaluate(
        """b => {
            const d = document.createElement('div');
            d.style.cssText = `position:fixed;left:${b.x}px;top:${b.y}px;
              width:${b.width}px;height:${b.height}px;border:3px solid red;
              box-sizing:border-box;z-index:99999;pointer-events:none`;
            document.body.appendChild(d);
        }""",
        bbox,
    )


# ---------- step execution ----------
class StepFailure(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def locate(page, target):
    return page.get_by_role(target["role"], name=target["name"], exact=True)


def exists_anywhere(page, target):
    """How many elements match, INCLUDING ones hidden inside collapsed menus.
    (Normal role queries skip elements hidden from the accessibility tree.)"""
    return page.get_by_role(
        target["role"], name=target["name"], exact=True, include_hidden=True).count()


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


# ---------- diagnosis (M2) ----------
def diagnose(page, step, reason, base_entry):
    """Turn a raw failure reason into WHAT changed.
    Returns {label, confidence, evidence}. Deterministic, no LLM."""
    base_entry = base_entry or {}
    target = step.get("target")
    bbox = base_entry.get("bbox")

    # 1) The element is there but can't be used.
    if reason == "target_not_clickable":
        disabled = locate(page, target).first.is_disabled()
        return {"label": "DISABLED", "confidence": 0.9 if disabled else 0.5,
                "evidence": {"is_disabled": disabled}}

    # 2) The element could not be seen at its place.
    if reason == "target_not_found_or_hidden":
        matches = exists_anywhere(page, target)
        if matches > 0:  # exists in the page but is not visible -> collapsed menu
            return {"label": "MOVED", "confidence": 0.85,
                    "evidence": {"exists_but_hidden": True, "matches": matches,
                                 "hint": "probably inside a collapsed menu or panel"}}
        if bbox:  # same kind of element sitting where the old one was?
            best, best_score = None, 0.0
            for el in page.get_by_role(target["role"]).all():
                if not el.is_visible():
                    continue
                box = el.bounding_box()
                score = iou(bbox, box) if box else 0.0
                if score > best_score:
                    best, best_score = el, score
            if best is not None and best_score >= RENAME_IOU:
                new_name = (best.inner_text() or best.get_attribute("aria-label") or "").strip()
                return {"label": "RENAMED", "confidence": round(min(0.95, 0.5 + best_score / 2), 2),
                        "evidence": {"old_name": target["name"], "new_name": new_name,
                                     "overlap": round(best_score, 2)}}
        return {"label": "REMOVED", "confidence": 0.8,
                "evidence": {"matches": 0, "reason": "nothing similar at the old position"}}

    # 3) The action worked but the promised result did not happen.
    if reason == "outcome_not_met":
        expect = step.get("expect") or {}
        if "url_contains" in expect and expect["url_contains"] not in page.url:
            return {"label": "WRONG_DESTINATION", "confidence": 0.9,
                    "evidence": {"expected_url_part": expect["url_contains"],
                                 "actual_url": page.url}}
        now = controls(page.locator("body").aria_snapshot())
        new_controls = sorted(n for _, n in now - controls(base_entry.get("aria")))
        if new_controls:
            return {"label": "NEW_STEP_REQUIRED", "confidence": 0.75,
                    "evidence": {"new_controls": new_controls}}
        return {"label": "OUTCOME_CHANGED", "confidence": 0.5, "evidence": {}}

    return {"label": "UNKNOWN", "confidence": 0.0, "evidence": {}}


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
            entry["aria"] = page.locator("body").aria_snapshot()  # state AFTER the step
            record[step["id"]] = entry
        browser.close()
    (out / "baseline.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


# ---------- replay ----------
def run_tutorial(tutorial, base_url, mutation=None, out_dir="out/run",
                 baseline_path=BASELINE_PATH):
    """Replay all steps. Returns a list of per-step result dicts. A failed step
    carries a diagnosis and a screenshot with the old position outlined in red."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    baseline = load_baseline(baseline_path)
    set_mutation(base_url, mutation)
    results, failed = [], False
    with sync_playwright() as p:
        browser, page = new_page(p)
        for step in tutorial["steps"]:
            res = {"id": step["id"], "status": "SKIPPED", "reason": None,
                   "seconds": 0.0, "diagnosis": None}
            if not failed:
                t0 = time.time()
                try:
                    do_step(page, step, base_url)
                    res["status"] = "PASS"
                except StepFailure as e:
                    failed = True
                    entry = baseline.get(step["id"], {})
                    res["status"], res["reason"] = "FAIL", e.reason
                    res["diagnosis"] = diagnose(page, step, e.reason, entry)
                    outline(page, entry.get("bbox"))
                    shot = out / f"{step['id']}_{mutation or 'clean'}_FAIL.png"
                    page.screenshot(path=str(shot))
                    res["screenshot"] = str(shot)
                    res["baseline_bbox"] = entry.get("bbox")
                    res["baseline_screenshot"] = str(
                        Path("out/baseline") / f"{step['id']}_before.png")
                res["seconds"] = round(time.time() - t0, 2)
            results.append(res)
        browser.close()
    set_mutation(base_url, None)
    return results


def first_failure(results):
    return next((r for r in results if r["status"] == "FAIL"), None)
