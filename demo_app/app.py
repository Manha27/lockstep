"""Tiny demo web app. Mutations are stored on the SERVER, so they survive
page navigation (unlike ?mutation= URL parameters)."""
import time
from flask import Flask, render_template_string

app = Flask(__name__)
STATE = {"mutation": None}

MUTATIONS = {
    # --- M1/M2 set ---
    "move_export", "rename_export", "remove_export", "disable_export",
    "add_confirm", "rename_reports_nav", "wrong_route",
    "slow_export", "harmless_restyle",
    # --- M3: harder / subtler cases ---
    "same_label_new_page",   # label unchanged, but the button now goes elsewhere
    "renamed_and_moved",     # renamed AND hidden inside a menu at the same time
    "blocked_overlay",       # cookie popup covers the page
    "changed_banner_text",   # works, but the success message changed
    "duplicate_export",      # two identical "Export to CSV" buttons
    "late_button",           # button appears after 1.2s (still within tolerance)
    "reorder_nav",           # nav order changed (harmless)
}

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Demo App</title>
<style>
  *, *::before, *::after { animation: none !important; transition: none !important; }
  body { font-family: system-ui, sans-serif; margin: 0; background: #fafafa; color: #222; }
  nav { background: #1d1d2b; padding: 14px 24px; display: flex; gap: 20px; }
  nav a { color: #fff; text-decoration: none; }
  main { padding: 32px 24px; max-width: 760px; }
  button { padding: 10px 16px; font-size: 15px; cursor: pointer; }
  .banner { background: #e6f7ea; border: 1px solid #9bd5a8; padding: 10px; margin: 16px 0; }
  .modal { border: 2px solid #333; background: #fff; padding: 20px; margin: 16px 0; }
  .fancy { background: #6c4bd6; color: #fff; border: 0; border-radius: 8px; }
  .overlay { position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 50;
             display: flex; align-items: center; justify-content: center; }
</style></head><body>
<nav>{{ nav|safe }}</nav>
<main>{{ body|safe }}</main>
</body></html>"""


def render(body):
    m = STATE["mutation"]
    label = "Analytics" if m == "rename_reports_nav" else "Reports"
    href = "/coming-soon" if m == "wrong_route" else "/reports"
    links = [("/", "Dashboard"), (href, label), ("/settings", "Settings")]
    if m == "reorder_nav":
        links = [links[2], links[1], links[0]]
    nav = "".join(f'<a href="{h}">{t}</a>' for h, t in links)
    return render_template_string(PAGE, body=body, nav=nav)


def form(label, extra="", action="/reports/export", method="post"):
    return (f'<form method="{method}" action="{action}">'
            f'<button type="submit" {extra}>{label}</button></form>')


def export_widget():
    m = STATE["mutation"]
    if m == "remove_export":
        return ""
    if m == "rename_export":
        return form("Download CSV")
    if m == "disable_export":
        return form("Export to CSV", "disabled")
    if m == "move_export":
        return "<details><summary>More actions</summary>" + form("Export to CSV") + "</details>"
    if m == "renamed_and_moved":
        return "<details><summary>More actions</summary>" + form("Download CSV") + "</details>"
    if m == "harmless_restyle":
        return form("Export to CSV", 'class="fancy"')
    if m == "same_label_new_page":
        return form("Export to CSV", action="/coming-soon", method="get")
    if m == "duplicate_export":
        return form("Export to CSV") + form("Export to CSV")
    if m == "late_button":
        return ('<div id="slot"></div><script>setTimeout(function(){document.getElementById("slot").innerHTML='
                + repr(form("Export to CSV")) + ';}, 1200);</script>')
    if m == "blocked_overlay":
        return (form("Export to CSV")
                + '<div class="overlay"><div class="modal"><p>We use cookies.</p>'
                  '<button type="button">Accept cookies</button></div></div>')
    if m == "add_confirm":
        return (
            '<button type="button" onclick="document.getElementById(\'m\').hidden=false">'
            "Export to CSV</button>"
            '<div id="m" class="modal" hidden><p>Are you sure?</p>'
            '<form method="post" action="/reports/export">'
            '<button type="submit">Confirm export</button></form></div>'
        )
    return form("Export to CSV")


@app.get("/")
def dashboard():
    return render("<h1>Dashboard</h1><p>Welcome back.</p>")


@app.get("/reports")
def reports():
    return render("<h1>Reports</h1><p>Monthly sales report.</p>" + export_widget())


@app.post("/reports/export")
def do_export():
    m = STATE["mutation"]
    if m == "slow_export":
        time.sleep(1.0)
    word = "Export complete" if m == "changed_banner_text" else "Export started"
    return render(
        "<h1>Reports</h1><p>Monthly sales report.</p>"
        f'<div class="banner">{word}: report.csv</div>' + export_widget()
    )


@app.get("/settings")
def settings():
    return render("<h1>Settings</h1><p>Nothing to see here.</p>")


@app.get("/coming-soon")
def coming_soon():
    return render("<h1>Coming soon</h1>")


@app.post("/__mutate/<name>")
def mutate(name):
    if name == "reset":
        STATE["mutation"] = None
    elif name in MUTATIONS:
        STATE["mutation"] = name
    else:
        return {"error": "unknown mutation"}, 400
    return {"mutation": STATE["mutation"]}


if __name__ == "__main__":
    app.run(port=5000, threaded=True)
