import threading
import webbrowser

from flask import Flask, redirect, render_template, request, send_file, url_for

import history_store
import read_seed
from generator import build_expense_report, suggest_filename

app = Flask(__name__)


@app.route("/")
def index():
    return render_template(
        "index.html",
        history=history_store.load_history(),
        projects=history_store.load_projects(),
        refreshed=request.args.get("refreshed"),
        added=request.args.get("added"),
    )


@app.route("/refresh_read_seed", methods=["POST"])
def refresh_read_seed():
    seed = read_seed.scan_read_folder()
    summary = history_store.merge_read_seed(seed)
    total_added = summary["history_added"] + summary["projects_added"]
    return redirect(url_for("index", refreshed=1, added=total_added))


@app.route("/generate", methods=["POST"])
def generate():
    form = request.form

    use_spec = "use_spec" in form
    use_unit = "use_unit" in form
    use_qty = "use_qty" in form
    use_price = "use_price" in form

    names = form.getlist("item_name[]")
    specs = form.getlist("item_spec[]")
    units = form.getlist("item_unit[]")
    qtys = form.getlist("item_qty[]")
    prices = form.getlist("item_price[]")
    supplies = form.getlist("item_supply[]")

    items = []
    for name, spec, unit, qty, price, supply in zip(names, specs, units, qtys, prices, supplies):
        if not name.strip():
            continue
        item = {"name": name.strip()}
        if use_spec:
            item["spec"] = spec.strip()
        if use_unit:
            item["unit"] = unit.strip()
        if use_qty:
            item["qty"] = float(qty) if qty.strip() else 0
        if use_price:
            item["price"] = float(price) if price.strip() else 0
        else:
            item["supply"] = float(supply) if supply.strip() else 0
        items.append(item)

    if not items:
        return "품목을 1개 이상 입력해주세요.", 400

    data = {
        "company": form.get("company", "").strip(),
        "doc_number": form.get("doc_number", "").strip(),
        "propose_date": form.get("propose_date", "").strip(),
        "spend_date": form.get("spend_date", "").strip(),
        "department": form.get("department", "그린연구소").strip() or "그린연구소",
        "requester": form.get("requester", "").strip(),
        "title": form.get("title", "").strip(),
        "detail": form.get("detail", "").strip(),
        "agency": form.get("agency", "").strip(),
        "org": form.get("org", "").strip(),
        "project_name": form.get("project_name", "").strip(),
        "execution_note": form.get("execution_note", "").strip(),
        "items": items,
    }

    buffer = build_expense_report(data)
    filename = suggest_filename(data)
    history_store.record_generation(data)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def _open_browser():
    webbrowser.open("http://127.0.0.1:5000")


if __name__ == "__main__":
    threading.Timer(1.0, _open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
