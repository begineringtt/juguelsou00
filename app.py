import threading
import webbrowser

from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for

import column_settings
import history_store
import read_seed
from generator import build_expense_report, suggest_filename
from pdf_item_parser import parse_pdf_items

app = Flask(__name__)


@app.route("/")
def index():
    projects = history_store.load_projects()
    for p in projects:
        p["label"] = history_store.effective_label(p)
    return render_template(
        "index.html",
        history=history_store.load_history(),
        projects=projects,
        columns=column_settings.load_columns(),
        refreshed=request.args.get("refreshed"),
        added=request.args.get("added"),
    )


@app.route("/add_project", methods=["POST"])
def add_project():
    form = request.form
    project_name = form.get("project_name", "").strip()
    if not project_name:
        return jsonify({"error": "과제명을 입력해주세요."}), 400

    entry = history_store.add_project(
        agency=form.get("agency", ""),
        org=form.get("org", ""),
        project_name=project_name,
        label=form.get("label", ""),
    )
    entry["label"] = history_store.effective_label(entry)
    return jsonify(entry)


@app.route("/update_project", methods=["POST"])
def update_project():
    form = request.form
    project_name = form.get("project_name", "").strip()
    if not project_name:
        return jsonify({"error": "과제명을 입력해주세요."}), 400

    entry = history_store.update_project(
        original_name=form.get("original_name", ""),
        agency=form.get("agency", ""),
        org=form.get("org", ""),
        project_name=project_name,
        label=form.get("label", ""),
    )
    entry["label"] = history_store.effective_label(entry)
    return jsonify(entry)


@app.route("/delete_project", methods=["POST"])
def delete_project():
    project_name = request.form.get("project_name", "").strip()
    if not project_name:
        return jsonify({"error": "삭제할 과제명이 없습니다."}), 400
    deleted = history_store.delete_project(project_name)
    if not deleted:
        return jsonify({"error": "해당 과제를 찾을 수 없습니다."}), 404
    return jsonify({"ok": True})


@app.route("/refresh_read_seed", methods=["POST"])
def refresh_read_seed():
    seed = read_seed.scan_read_folder()
    summary = history_store.merge_read_seed(seed)
    total_added = summary["history_added"] + summary["projects_added"]
    return redirect(url_for("index", refreshed=1, added=total_added))


@app.route("/column_settings", methods=["GET"])
def get_column_settings():
    return jsonify({"columns": column_settings.load_columns()})


@app.route("/column_settings", methods=["POST"])
def save_column_settings_route():
    payload = request.get_json(silent=True) or {}
    columns = payload.get("columns")
    if not isinstance(columns, list):
        return jsonify({"error": "columns가 필요합니다."}), 400
    column_settings.save_columns(columns)
    return jsonify({"columns": columns})


@app.route("/column_settings/add", methods=["POST"])
def add_column_setting():
    label = request.form.get("label", "").strip()
    if not label:
        return jsonify({"error": "항목 이름을 입력해주세요."}), 400
    entry = column_settings.add_custom_column(label)
    return jsonify({"column": entry, "columns": column_settings.load_columns()})


@app.route("/column_settings/enable", methods=["POST"])
def set_column_enabled_route():
    key = request.form.get("key", "")
    if not key:
        return jsonify({"error": "key가 필요합니다."}), 400
    enabled = request.form.get("enabled") == "1"
    columns = column_settings.set_column_enabled(key, enabled)
    return jsonify({"columns": columns})


@app.route("/column_settings/delete", methods=["POST"])
def delete_column_setting():
    key = request.form.get("key", "")
    if not key:
        return jsonify({"error": "key가 필요합니다."}), 400
    deleted = column_settings.delete_column(key)
    if not deleted:
        return jsonify({"error": "삭제할 수 없는 항목입니다."}), 400
    return jsonify({"columns": column_settings.load_columns()})


@app.route("/parse_pdf", methods=["POST"])
def parse_pdf():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "파일이 없습니다."}), 400
    extra_fields = {
        c["key"]: [c["label"]]
        for c in column_settings.load_columns()
        if not c.get("builtin") and c.get("enabled")
    }
    try:
        result = parse_pdf_items(file.read(), extra_fields=extra_fields or None)
    except Exception:
        return jsonify({"error": "PDF를 읽을 수 없습니다. 파일이 손상되었거나 PDF 형식이 아닐 수 있습니다."}), 400
    return jsonify(result)


@app.route("/generate", methods=["POST"])
def generate():
    form = request.form
    columns = column_settings.load_columns()

    names = form.getlist("item_name[]")
    supplies = form.getlist("item_supply[]")
    active_values = {
        c["key"]: form.getlist(f"item_{c['key']}[]")
        for c in columns
        if f"use_{c['key']}" in form
    }

    items = []
    try:
        for idx, name in enumerate(names):
            if not name.strip():
                continue
            item = {"name": name.strip()}
            for key, values in active_values.items():
                raw = values[idx] if idx < len(values) else ""
                if key in ("qty", "weight", "price"):
                    item[key] = float(raw) if raw.strip() else 0
                else:
                    item[key] = raw.strip()
            if "price" not in item:
                supply_raw = supplies[idx] if idx < len(supplies) else ""
                item["supply"] = float(supply_raw) if supply_raw.strip() else 0
            items.append(item)
    except ValueError:
        return "수량/단가/공급가는 숫자로 입력해주세요.", 400

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

    try:
        buffer = build_expense_report(data)
    except ValueError as e:
        return str(e), 400
    except Exception as e:
        return f"엑셀 생성 중 오류가 발생했습니다: {type(e).__name__}: {e}", 500
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
