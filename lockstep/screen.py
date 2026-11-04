"""Build the self-contained Video Health screen (one HTML file, no server)
from out/results.json, the tutorial file, and the saved screenshots."""
import base64
import json
from pathlib import Path

import yaml

TEMPLATE = Path(__file__).with_name("video_health_template.html")


def _data_uri(path):
    p = Path(path) if path else None
    if not p or not p.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def build_screen(tutorial_path, results_path="out/results.json", out_path="out/video_health.html"):
    results = json.loads(Path(results_path).read_text(encoding="utf-8"))
    tut = yaml.safe_load(Path(tutorial_path).read_text(encoding="utf-8"))
    steps = [{"id": s["id"], "intent": s.get("intent", s["id"]), "narration": s.get("narration"),
              "target_name": (s.get("target") or {}).get("name")} for s in tut["steps"]]
    images = {}
    for c in results["cases"]:
        for key in ("baseline_screenshot", "failure_screenshot"):
            if c.get(key) and c[key] not in images:
                images[c[key]] = _data_uri(c[key])
    payload = {"tutorial": tut.get("name", "Tutorial"), "steps": steps,
               "cases": results["cases"], "summary": results["summary"], "images": images}
    blob = json.dumps(payload).replace("</", "<\\/")
    html = TEMPLATE.read_text(encoding="utf-8").replace("/*__DATA__*/null", blob)
    out = Path(out_path)
    out.parent.mkdir(exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out
