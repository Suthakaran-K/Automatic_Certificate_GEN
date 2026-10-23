from flask import g
from sqlalchemy import create_engine, text
from config import Config
from pathlib import Path
import os

_engine = None


def _database_url():
    """Return a SQLAlchemy URL, defaulting to a local SQLite database."""
    url = (Config.DATABASE_URL or "").strip()
    if url:
        # Accept the generic MySQL URL, but explicitly select SQLAlchemy's PyMySQL driver.
        if url.startswith("mysql://"):
            url = "mysql+pymysql://" + url[len("mysql://"):]
        return url
    return "sqlite:///" + str(Path(__file__).resolve().parent / "certificates.db")


def _connect_args(url):
    """Build driver options for SQLite or a TLS-verified TiDB/MySQL connection."""
    if url.startswith("sqlite"):
        return {"check_same_thread": False}

    # PyMySQL supports certificate and hostname verification. If TiDB provides a
    # CA certificate, set TIDB_CA_PATH in Render to its absolute path.
    args = {
        "ssl_verify_cert": True,
        "ssl_verify_identity": True,
    }
    ca_path = os.getenv("TIDB_CA_PATH", "").strip()
    if ca_path:
        if not Path(ca_path).is_file():
            raise RuntimeError(
                "TIDB_CA_PATH is set but the CA certificate file does not exist: " + ca_path
            )
        args["ssl_ca"] = ca_path
    return args


def get_engine():
    global _engine
    if _engine is None:
        url = _database_url()
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args=_connect_args(url),
            pool_recycle=1800,
        )
    return _engine


def init_db():
    engine = get_engine()
    if engine.dialect.name == "sqlite":
        ddl = """
        CREATE TABLE IF NOT EXISTS certificates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_name TEXT NOT NULL,
            email TEXT NOT NULL,
            event_name TEXT NOT NULL,
            certificate_type TEXT NOT NULL,
            pdf_filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            email_status TEXT NOT NULL DEFAULT 'Pending',
            email_error TEXT
        )
        """
    else:
        ddl = """
        CREATE TABLE IF NOT EXISTS certificates (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            participant_name VARCHAR(255) NOT NULL,
            email VARCHAR(320) NOT NULL,
            event_name VARCHAR(255) NOT NULL,
            certificate_type VARCHAR(40) NOT NULL,
            pdf_filename VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            email_status VARCHAR(20) NOT NULL DEFAULT 'Pending',
            email_error TEXT
        )
        """

    with engine.begin() as conn:
        conn.execute(text(ddl))
        # CREATE INDEX IF NOT EXISTS is not supported by all MySQL-compatible
        # servers. Check first, then create; ignore only an already-existing index.
        if engine.dialect.name == "sqlite":
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS idx_certificates_email ON certificates(email)"
            ))
        else:
            index_exists = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.statistics
                WHERE table_schema = DATABASE()
                  AND table_name = 'certificates'
                  AND index_name = 'idx_certificates_email'
            """)).scalar_one()
            if not index_exists:
                conn.execute(text(
                    "CREATE INDEX idx_certificates_email ON certificates(email)"
                ))


def get_db():
    if "db_conn" not in g:
        g.db_conn = get_engine().connect()
    return g.db_conn


def close_db(exception=None):
    conn = g.pop("db_conn", None)
    if conn is not None:
        conn.close()


def row_to_dict(row):
    # SQLAlchemy Row objects expose their mapping through _mapping.
    data = dict(row._mapping) if hasattr(row, "_mapping") else dict(row)
    if data.get("created_at") is not None:
        data["created_at"] = str(data["created_at"])
    return data
