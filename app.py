import json
import os
import tempfile
import threading
import webbrowser

from flask import Flask, jsonify, redirect, render_template, request, send_file, url_for

import automation
import column_settings
import history_store
import quote_reader
import read_seed
from generator import build_expense_report, suggest_filename
from paths import app_dir
from pdf_item_parser import parse_pdf_items

app = Flask(__name__)

_CONFIG_PATH = os.path.join(app_dir(), "data", "app_config.json")


def _load_config():
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def _save_config(cfg):
    os.makedirs(os.path.dirname(_CONFIG_PATH), exist_ok=True)
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


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


DEFAULT_SETTING03 = r"D:\claude_personal\setting_03"


@app.route("/batch", methods=["GET"])
def batch_page():
    cfg = _load_config()
    projects = history_store.load_projects()
    for p in projects:
        p["label"] = history_store.effective_label(p)
    return render_template(
        "batch.html",
        projects=projects,
        setting03_root=cfg.get("setting03_root", "") or DEFAULT_SETTING03,
    )


@app.route("/batch_parse_quote", methods=["POST"])
def batch_parse_quote():
    file = request.files.get("quote")
    if not file or not file.filename:
        return jsonify({"error": "파일이 없습니다."}), 400
    ext = os.path.splitext(file.filename)[1]
    try:
        result = quote_reader.read_quote(data_bytes=file.read(), ext=ext)
    except Exception:
        return jsonify({"error": "견적서를 읽을 수 없습니다."}), 400
    return jsonify({
        "company": result.get("company"),
        "title": result.get("title"),
        "warnings": result.get("warnings", []),
    })


def _save_upload(file_storage):
    """업로드 파일을 임시 폴더에 원래 확장자로 저장하고 경로 반환."""
    if not file_storage or not file_storage.filename:
        return None
    ext = os.path.splitext(file_storage.filename)[1]
    fd, path = tempfile.mkstemp(suffix=ext)
    os.close(fd)
    file_storage.save(path)
    return path


@app.route("/batch_run", methods=["POST"])
def batch_run():
    form = request.form
    setting03_root = form.get("setting03_root", "").strip()
    category = form.get("category", "").strip()
    company = form.get("company", "").strip()
    if not (setting03_root and category and company):
        return jsonify({"error": "setting_03 경로 / 카테고리 / 업체명은 필수입니다."}), 400
    if not os.path.isdir(setting03_root):
        return jsonify({"error": f"setting_03 경로를 찾을 수 없습니다: {setting03_root}"}), 400

    # 설정 저장(다음 실행 때 경로 자동 채움)
    cfg = _load_config()
    cfg["setting03_root"] = setting03_root
    _save_config(cfg)

    quote_path = _save_upload(request.files.get("quote"))
    if not quote_path:
        return jsonify({"error": "견적서 파일을 첨부해주세요."}), 400

    attachments = {}
    for field, label in (("biz", "사업자등록증"), ("bank", "통장사본"),
                         ("tax", "전자세금계산서"), ("statement", "거래명세서")):
        p = _save_upload(request.files.get(field))
        if p:
            attachments[label] = p

    try:
        manifest = automation.run(
            quote_path, category, company, setting03_root,
            inspector=form.get("inspector", "").strip(),
            inspect_date=form.get("inspect_date", "").strip() or None,
            requester=form.get("requester", "").strip(),
            product=form.get("product", "").strip() or None,
            attachments=attachments,
            place=(form.get("dry_run") != "1"),
        )
    except Exception as e:
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 500

    # 직렬화 가능한 요약만 반환
    return jsonify({
        "company": manifest["company"],
        "category": manifest["category"],
        "category_folder": manifest["category_folder"],
        "target_folder_name": manifest["target_folder_name"],
        "target_folder_is_new": manifest["target_folder_is_new"],
        "target_dir": manifest.get("target_dir"),
        "item_count": manifest["item_count"],
        "total_supply": manifest["total_supply"],
        "quote_source": manifest["quote_source"],
        "items": manifest["items"],
        "warnings": manifest["warnings"],
        "pdf_error": manifest.get("pdf_error"),
        "placed_files": manifest.get("placed_files", []),
        "attachments_from_repo": manifest.get("attachments_from_repo", {}),
        "checklist": manifest.get("checklist"),
        "report_path": manifest.get("report_path"),
    })


def _open_browser():
    # 기본 화면을 '견적서 자동 정리(/batch)'로 연다.
    webbrowser.open("http://127.0.0.1:5000/batch")


if __name__ == "__main__":
    threading.Timer(1.0, _open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
