# Automated Digital Certificate Generator

A Flask web app for validating CSV/XLSX participant lists, selecting one of three original certificate templates, generating personalized PDF files, storing records in SQLite or TiDB Cloud (MySQL-compatible), emailing PDFs through Gmail SMTP, and retrying failed email delivery.

## Important before you deploy

- The project does **not** contain invented certificate artwork. Supply the three original files: `participation.png`, `first_prize.png`, and `second_prize.png`.
- Configure the text coordinates in `certificate_generator.py` for your template designs before issuing real certificates.
- This starter app does not include administrator login. Do not expose it publicly until you add authentication or restrict access. The upload, generation, and template-replacement endpoints can otherwise be used by anyone who can reach the site.
- Render's normal filesystem is ephemeral. If deployed on Render, attach a persistent disk for `generated_certificates/` and `templates_certificates/`, or change storage to object storage. A disk is tied to one service instance and may not be available on every plan.
- The batch preview is held in process memory; for multiple instances or large workloads, use a persistent job queue/store.
- The app avoids recreating an already-recorded participant/event/type with a PDF, but production duplicate handling should use a unique batch idempotency key and a database unique constraint.

## Folder structure

```text
automated_certificate_generator/
├── app.py
├── config.py
├── database.py
├── certificate_generator.py
├── email_service.py
├── spreadsheet_service.py
├── requirements.txt
├── .env.example
├── .gitignore
├── render.yaml
├── README.md
├── certificates.db                 # created automatically locally; do not commit
├── templates_certificates/
│   └── README.md                   # place the three original template images here
├── generated_certificates/         # generated PDFs
├── uploads/                        # temporary uploads
├── static/
│   ├── css/style.css
│   ├── js/script.js
│   └── sample_participants.csv
├── templates/index.html
└── tests/test_spreadsheet_service.py
```

## 1. Run locally in VS Code

Use Python 3.11 or 3.12.

### Windows PowerShell

```powershell
py -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

### macOS/Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Open `http://127.0.0.1:5000`.

SQLite is used automatically when `DATABASE_URL` is blank. The database table is created on startup.

## 2. Add original templates

Place these exact filenames in `templates_certificates/`:

- `participation.png`
- `first_prize.png`
- `second_prize.png`

Or use the Template section in the dashboard to upload each image. PNG/JPG images are supported. Keep the originals at high resolution. The text overlay positions are example configuration values, not guaranteed to match your artwork. Edit `TEXT_LAYOUT` in `certificate_generator.py` to tune each template's name/event/award/date positions. Coordinates are proportions from the top-left (0 to 1).

If your source template is a PDF, export/render the relevant page to a high-resolution PNG first (for example, 300 DPI) using a PDF viewer or an approved PDF-to-image utility.

## 3. Configure Gmail email

1. Enable 2-Step Verification on the Google account that will send the certificates.
2. Create a Google App Password in the account's security settings (if the account is eligible).
3. Copy `.env.example` to `.env` and set `SMTP_USERNAME`, `SMTP_PASSWORD`, and `MAIL_FROM`.
4. Never commit `.env` or paste the app password into frontend code.
5. Initially test with a spreadsheet containing only addresses you control. The example CSV uses reserved example.com addresses and will not deliver to real mailboxes.

Email is marked Sent only after SMTP accepts the message. A successful SMTP submission does not guarantee final inbox delivery.

## 4. Use the application

1. Open the dashboard.
2. Upload an `.xlsx` or `.csv` file with required columns `Name`, `Email`, `Event Name`, `Certificate Type`. Optional `Issue Date` is supported.
3. Review the validation preview; invalid rows are skipped.
4. Click **Generate PDFs & send emails**.
5. Search/filter the certificate table, download a PDF, or retry a failed email.

Recognized certificate types include Participation, 1st Prize/First Prize, and 2nd Prize/Second Prize.

## 5. Use TiDB Cloud (MySQL-compatible)

1. Create a TiDB Cloud cluster and a database in the TiDB SQL editor.
2. In TiDB Cloud, open the connection details for your cluster and choose the MySQL-compatible connection method.
3. Obtain the host, port, username, password, database name, and TLS/CA requirements from the TiDB Cloud connection screen.
4. Set `DATABASE_URL` to the SQLAlchemy PyMySQL format. Example shape (replace every value and follow the TLS instructions shown by TiDB Cloud):

```text
mysql+pymysql://USERNAME:PASSWORD@HOST:4000/DATABASE
```

If credentials contain URL-reserved characters, URL-encode them. The application enables TLS certificate and hostname verification for MySQL/TiDB connections. If your TiDB Cloud Connect dialog supplies a CA certificate, make it available to the service and set `TIDB_CA_PATH` to its absolute file path in Render. Do not disable TLS to work around a connection problem.

5. Install requirements and restart the app. The table and email index are created automatically in the configured database.

For local development with TiDB, set `DATABASE_URL` in `.env`. In Render, add the same variable under the web service's Environment settings rather than uploading `.env`.

## 6. Deploy to GitHub and Render

1. Extract this ZIP.
2. Add your three template images to `templates_certificates/` (or upload them after deployment only once access is secured).
3. Create a private GitHub repository if the project contains any sensitive configuration or real templates.
4. Commit the source. Do **not** commit `.env`, database files, real participant lists, or generated certificates.
5. Push the project to GitHub.
6. In Render, create a **Web Service** from the repository. Render can use `render.yaml`, or set:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
7. Add environment variables in Render: `DATABASE_URL`, `SECRET_KEY`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `MAIL_FROM`.
8. Add a persistent disk if you want generated PDFs and template files to survive deploys/restarts. Configure `OUTPUT_FOLDER` and `TEMPLATE_FOLDER` to paths under the mounted disk.
9. Deploy and open the Render URL. Test with a controlled email address first.

## 7. Test

```bash
pytest -q
```

The included tests cover certificate-type normalization, email validation, missing required columns, and mixed valid/invalid row parsing. They do not test real Gmail delivery, TiDB connectivity, or Render deployment; those require your own credentials and environment. Before production, add authentication, CSRF protection, rate limiting, persistent storage/job handling, and integration tests.

## API routes

- `GET /` — dashboard
- `POST /api/upload` — upload/validate spreadsheet (`file`)
- `GET /api/preview?batch_id=...` — retrieve a preview
- `POST /api/generate` — process uploaded batch (`{"batch_id":"..."}`)
- `GET /api/certificates` — list/search/filter records (`q`, `type`)
- `GET /api/certificates/<id>/download` — download PDF
- `POST /api/certificates/<id>/retry-email` — retry email
- `GET /api/dashboard` — summary metrics
- `GET /api/templates` — template status
- `POST /api/templates/<type>` — replace a template (`Participation`, `First Prize`, `Second Prize`)

## Troubleshooting

- **Missing template**: upload the matching original template image.
- **Email failed**: verify Gmail App Password, SMTP variables, network access, and sender account restrictions.
- **TiDB connection failed**: re-check host/port/database credentials and the TLS CA settings copied from TiDB Cloud.
- **No PDFs after deploy/restart**: configure persistent disk or object storage.
- **Certificate text is misplaced**: edit `TEXT_LAYOUT` and the font-size settings in `certificate_generator.py`.

## License and data note

Use only certificate designs, participant information, and email addresses you are authorized to process. Keep the app private until authentication is implemented.
