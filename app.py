import os
import uuid
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file, abort
from werkzeug.utils import secure_filename
from sqlalchemy import text

from config import Config
from database import init_db, get_db, close_db, row_to_dict
from spreadsheet_service import parse_spreadsheet
from certificate_generator import generate_certificate, TEMPLATE_FILES
from email_service import send_certificate_email


app = Flask(__name__)
app.config.from_object(Config)
app.teardown_appcontext(close_db)

for folder in (app.config["UPLOAD_FOLDER"], app.config["OUTPUT_FOLDER"], app.config["TEMPLATE_FOLDER"]):
    Path(folder).mkdir(parents=True, exist_ok=True)

init_db()
pending_batches = {}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/dashboard")
def dashboard():
    db = get_db()
    rows = db.execute(text("""
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN pdf_filename IS NOT NULL AND pdf_filename <> '' THEN 1 ELSE 0 END) AS generated_count,
               SUM(CASE WHEN email_status = 'Sent' THEN 1 ELSE 0 END) AS sent,
               SUM(CASE WHEN email_status = 'Failed' THEN 1 ELSE 0 END) AS failed
        FROM certificates
    """)).mappings().first()
    return jsonify({
        "total": int(rows["total"] or 0),
        "generated": int(rows["generated_count"] or 0),
        "sent": int(rows["sent"] or 0),
        "failed": int(rows["failed"] or 0),
        "invalid_rows": 0,
    })


@app.post("/api/upload")
def upload_spreadsheet():
    if "file" not in request.files:
        return jsonify(error="Choose an .xlsx or .csv file."), 400
    file = request.files["file"]
    filename = secure_filename(file.filename or "")
    ext = Path(filename).suffix.lower()
    if ext not in {".xlsx", ".csv"}:
        return jsonify(error="Only .xlsx and .csv files are supported."), 400
    saved = Path(app.config["UPLOAD_FOLDER"]) / f"{uuid.uuid4().hex}_{filename}"
    file.save(saved)
    try:
        result = parse_spreadsheet(saved)
    except ValueError as exc:
        saved.unlink(missing_ok=True)
        return jsonify(error=str(exc)), 400
    except Exception:
        saved.unlink(missing_ok=True)
        app.logger.exception("Spreadsheet parsing failed")
        return jsonify(error="Could not read the spreadsheet. Check that it is a valid CSV/XLSX file."), 400
    batch_id = uuid.uuid4().hex
    pending_batches[batch_id] = result
    return jsonify({
        "batch_id": batch_id,
        "total_rows": len(result["rows"]),
        "valid_rows": sum(1 for r in result["rows"] if r["valid"]),
        "invalid_rows": sum(1 for r in result["rows"] if not r["valid"]),
        "rows": result["rows"][:200],
        "errors": result["errors"],
    })


@app.get("/api/preview")
def preview():
    batch_id = request.args.get("batch_id", "")
    batch = pending_batches.get(batch_id)
    if not batch:
        return jsonify(error="Upload not found or expired. Please upload the spreadsheet again."), 404
    return jsonify(rows=batch["rows"][:200], errors=batch["errors"])


@app.post("/api/generate")
def generate():
    payload = request.get_json(silent=True) or {}
    batch_id = payload.get("batch_id", "")
    batch = pending_batches.get(batch_id)
