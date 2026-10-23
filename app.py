import os
from flask import Flask, render_template, request, jsonify, send_file, abort
from werkzeug.utils import secure_filename
from config import Config
from database import init_db, get_db, close_db, row_to_dict
from spreadsheet_service import parse_spreadsheet
from certificate_generator import generate_certificate, TEMPLATE_FILES
from email_service import send_certificate_email
from sqlalchemy import text
from pathlib import Path
import uuid

app = Flask(__name__)
app.config.from_object(Config)
app.teardown_appcontext(close_db)

for folder in (app.config["UPLOAD_FOLDER"], app.config["OUTPUT_FOLDER"], app.config["TEMPLATE_FOLDER"]):
    Path(folder).mkdir(parents=True, exist_ok=True)

init_db()

# Parsed upload data is kept in memory for this simple single-instance starter app.
# For multi-instance/production workloads, use Redis or persistent job storage.
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
        "invalid_rows": 0
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
        "errors": result["errors"]
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
    if not batch:
        return jsonify(error="Upload not found or expired. Please upload it again."), 404

    db = get_db()
    summary = {"total_rows": len(batch["rows"]), "valid_rows": 0, "invalid_rows": 0,
               "generated": 0, "emails_sent": 0, "emails_failed": 0, "row_errors": []}
    for item in batch["rows"]:
        if not item["valid"]:
            summary["invalid_rows"] += 1
            continue
        summary["valid_rows"] += 1
        participant = item["data"]
        # Avoid duplicate records for the same participant/event/type.
        existing = db.execute(text("""
            SELECT id, pdf_filename FROM certificates
            WHERE email=:email AND event_name=:event AND certificate_type=:ctype
              AND participant_name=:name
            ORDER BY id DESC LIMIT 1
        """), {"email": participant["Email"].lower(), "event": participant["Event Name"],
               "ctype": participant["Certificate Type"], "name": participant["Name"]}).mappings().first()
        if existing and existing["pdf_filename"]:
            continue
        try:
            pdf_path = generate_certificate(
                participant_name=participant["Name"],
                event_name=participant["Event Name"],
                certificate_type=participant["Certificate Type"],
                template_folder=app.config["TEMPLATE_FOLDER"],
                output_folder=app.config["OUTPUT_FOLDER"],
                issue_date=participant.get("Issue Date", "")
            )
            pdf_name = Path(pdf_path).name
            result = db.execute(text("""
                INSERT INTO certificates
                (participant_name, email, event_name, certificate_type, pdf_filename, email_status, email_error)
                VALUES (:name, :email, :event, :ctype, :pdf, 'Pending', NULL)
            """), {"name": participant["Name"], "email": participant["Email"].lower(),
                   "event": participant["Event Name"], "ctype": participant["Certificate Type"], "pdf": pdf_name})
            db.commit()
            cert_id = result.lastrowid
            try:
                send_certificate_email(
                    to_email=participant["Email"].lower(),
                    participant_name=participant["Name"],
                    event_name=participant["Event Name"],
                    pdf_path=pdf_path
                )
                db.execute(text("UPDATE certificates SET email_status='Sent', email_error=NULL WHERE id=:id"), {"id": cert_id})
                summary["emails_sent"] += 1
            except Exception as exc:
                app.logger.warning("Email failed for certificate id %s: %s", cert_id, exc)
                db.execute(text("UPDATE certificates SET email_status='Failed', email_error=:err WHERE id=:id"),
                           {"err": str(exc)[:1000], "id": cert_id})
                summary["emails_failed"] += 1
            db.commit()
            summary["generated"] += 1
        except Exception as exc:
            db.rollback()
            app.logger.exception("Certificate generation failed")
            summary["row_errors"].append({"name": participant.get("Name", ""), "error": str(exc)})
    pending_batches.pop(batch_id, None)
    return jsonify(summary)

@app.get("/api/certificates")
def certificates():
    db = get_db()
    q = request.args.get("q", "").strip()
    ctype = request.args.get("type", "").strip()
    sql = "SELECT * FROM certificates WHERE 1=1"
    params = {}
    if q:
        sql += " AND (LOWER(participant_name) LIKE :q OR LOWER(email) LIKE :q)"
        params["q"] = f"%{q.lower()}%"
    if ctype:
        sql += " AND certificate_type = :ctype"
        params["ctype"] = ctype
    sql += " ORDER BY id DESC LIMIT 500"
    rows = db.execute(text(sql), params).mappings().all()
    return jsonify([row_to_dict(row) for row in rows])

@app.get("/api/certificates/<int:certificate_id>/download")
def download_certificate(certificate_id):
    db = get_db()
    row = db.execute(text("SELECT pdf_filename FROM certificates WHERE id=:id"), {"id": certificate_id}).mappings().first()
    if not row or not row["pdf_filename"]:
        abort(404)
    filename = Path(row["pdf_filename"]).name
    path = Path(app.config["OUTPUT_FOLDER"]) / filename
    if not path.is_file():
        abort(404)
    return send_file(path, as_attachment=True, download_name=filename, mimetype="application/pdf")

@app.post("/api/certificates/<int:certificate_id>/retry-email")
def retry_email(certificate_id):
    db = get_db()
    row = db.execute(text("SELECT * FROM certificates WHERE id=:id"), {"id": certificate_id}).mappings().first()
    if not row:
        return jsonify(error="Certificate not found."), 404
    if row["email_status"] == "Sent":
        return jsonify(error="This email has already been sent."), 409
    path = Path(app.config["OUTPUT_FOLDER"]) / Path(row["pdf_filename"] or "").name
    if not path.is_file():
        return jsonify(error="The PDF file is missing. Regenerate the certificate from the original spreadsheet."), 404
    try:
        send_certificate_email(row["email"], row["participant_name"], row["event_name"], str(path))
        db.execute(text("UPDATE certificates SET email_status='Sent', email_error=NULL WHERE id=:id"), {"id": certificate_id})
        db.commit()
        return jsonify(status="Sent")
    except Exception as exc:
        db.execute(text("UPDATE certificates SET email_status='Failed', email_error=:err WHERE id=:id"),
                   {"err": str(exc)[:1000], "id": certificate_id})
        db.commit()
        return jsonify(error="Email delivery failed. Check SMTP configuration and try again."), 502

@app.get("/api/templates")
def template_status():
    folder = Path(app.config["TEMPLATE_FOLDER"])
    return jsonify([{"type": key, "filename": filename, "available": (folder / filename).is_file()}
                    for key, filename in TEMPLATE_FILES.items()])

@app.post("/api/templates/<template_type>")
def replace_template(template_type):
    if template_type not in TEMPLATE_FILES:
        return jsonify(error="Unsupported template type."), 404
    if "file" not in request.files:
        return jsonify(error="Choose a PNG or JPG template image."), 400
    file = request.files["file"]
    ext = Path(secure_filename(file.filename or "")).suffix.lower()
    if ext not in {".png", ".jpg", ".jpeg"}:
        return jsonify(error="Template must be PNG or JPG."), 400
    # Pillow verifies image content before replacing the template.
    from PIL import Image
    import io
    raw = file.read()
    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
    except Exception:
        return jsonify(error="The uploaded file is not a valid image."), 400
    target = Path(app.config["TEMPLATE_FOLDER"]) / TEMPLATE_FILES[template_type]
    target.write_bytes(raw)
    return jsonify(message=f"{TEMPLATE_FILES[template_type]} uploaded successfully.")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG") == "1")
