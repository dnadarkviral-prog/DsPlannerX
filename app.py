from __future__ import annotations

import calendar
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import shutil
import sqlite3
import time
import uuid
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "plannerx.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"

IS_VERCEL = bool(os.environ.get("VERCEL"))
if not IS_VERCEL:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = (os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or "").strip()
USE_POSTGRES = bool(DATABASE_URL)
BLOB_READ_WRITE_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip()
BLOB_ENABLED = bool(BLOB_READ_WRITE_TOKEN)
CLOUD_UPLOAD_ENABLED = IS_VERCEL and BLOB_ENABLED
TIMEZONE_NAME = os.environ.get("PLANNERX_TIMEZONE", "America/Sao_Paulo").strip() or "America/Sao_Paulo"
try:
    APP_TIMEZONE = ZoneInfo(TIMEZONE_NAME)
except Exception:
    TIMEZONE_NAME = "America/Sao_Paulo"
    APP_TIMEZONE = ZoneInfo(TIMEZONE_NAME)

ALLOWED_EXTENSIONS = {
    "mp4", "mov", "mkv", "avi", "webm", "m4v",
    "mp3", "wav", "m4a", "aac", "ogg", "flac",
    "png", "jpg", "jpeg", "webp", "gif", "svg",
    "txt", "md", "srt", "pdf",
}

STATUS_LABELS = {
    "production": "Em produção",
    "completed": "Concluído",
}

TITLE_STATUS_LABELS = {
    "ready": "Permitido para uso",
    "progress": "Em andamento",
    "completed": "Concluído",
}

FREQUENCY_MODES = {
    "interval": "Intervalo entre postagens",
    "days_off": "Dias completos sem postar",
}

PERIOD_MODES = {
    "months": "Mês(es) completo(s)",
    "days": "Quantidade exata de dias",
    "month_end": "Até o fim do mês escolhido",
}

SCHEDULE_MODES = {
    "standard": "Ritmo padrão",
    "custom": "Planejamento personalizado por mês",
}

PRODUCTION_LOG_STATUS = {
    "script_ready": "Roteiro pronto",
    "video_completed": "Vídeo concluído",
}

LOGIN_USERNAME = os.environ.get("PLANNERX_USERNAME", "Admdsscale")
LOGIN_PASSWORD = os.environ.get("PLANNERX_PASSWORD", "Acesso2626")
SESSION_SECRET_PATH = BASE_DIR / ".plannerx_session_key"

LOGIN_MOTIVATIONS = [
    "Login feito. Agora só falta convencer a lista de tarefas de que você veio trabalhar.",
    "Acesso liberado! O café entrou como gerente e a procrastinação perdeu o crachá.",
    "Bem-vinda de volta. Hoje a meta não escapa nem se trocar de thumbnail.",
    "Painel aberto: o algoritmo ainda não sabe, mas o dia dele acabou de ficar movimentado.",
    "Entrou no PlannerX. Respira, escolhe um card e finge que foi tudo planejado desde ontem.",
    "Acesso confirmado. Um roteiro por vez e, quando perceber, a meta já estará pedindo trégua.",
    "Sistema online. A criatividade chegou; agora estamos aguardando apenas o primeiro clique.",
    "Bem-vinda! Hoje vale produtividade, café e nenhuma reunião com a procrastinação.",
]


def load_session_secret() -> str:
    env_secret = os.environ.get("SESSION_SECRET", "").strip()
    if len(env_secret) >= 32:
        return env_secret
    if IS_VERCEL:
        # A tela de configuração avisa sobre a variável ausente. O fallback
        # evita falha de importação antes de o usuário concluir a configuração.
        return "ds-plannerx-vercel-session-secret-configure-no-painel"
    try:
        if SESSION_SECRET_PATH.exists():
            value = SESSION_SECRET_PATH.read_text(encoding="utf-8").strip()
            if len(value) >= 32:
                return value
        value = secrets.token_urlsafe(48)
        SESSION_SECRET_PATH.write_text(value, encoding="utf-8")
        return value
    except OSError:
        return "ds-plannerx-local-session-v2-1-fallback-key-change-me"


SESSION_SECRET = load_session_secret()


def password_matches(value: str) -> bool:
    return hmac.compare_digest(value, LOGIN_PASSWORD)


CONFIG_ERRORS: list[str] = []
if IS_VERCEL and not USE_POSTGRES:
    CONFIG_ERRORS.append("Conecte um banco Postgres/Neon e crie a variável DATABASE_URL.")
if IS_VERCEL and not BLOB_ENABLED:
    CONFIG_ERRORS.append("Crie um Vercel Blob Store para gerar BLOB_READ_WRITE_TOKEN.")
if IS_VERCEL and len(os.environ.get("SESSION_SECRET", "")) < 32:
    CONFIG_ERRORS.append("Crie SESSION_SECRET com pelo menos 32 caracteres.")

MONTH_NAMES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

app = FastAPI(title="DS - PLANNERX", docs_url=None, redoc_url=None)


def configuration_error_page() -> str:
    items = "".join(f"<li>{item}</li>" for item in CONFIG_ERRORS)
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Configurar DS - PLANNERX</title><style>
    body{{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at top,#32104f 0,#0b0711 45%,#050307 100%);color:#f5efff;font-family:Inter,Arial,sans-serif}}
    main{{width:min(720px,calc(100% - 40px));padding:34px;border:1px solid #6f3b91;border-radius:24px;background:rgba(15,9,22,.94);box-shadow:0 25px 80px #0008}}
    h1{{margin:0 0 12px;color:#d9b9ff}} p,li{{line-height:1.6;color:#d6c9e4}} code{{background:#241331;padding:3px 7px;border-radius:7px;color:#fff}}
    .tag{{display:inline-block;color:#bc6cff;font-weight:800;letter-spacing:.12em;font-size:12px;margin-bottom:10px}}
    </style></head><body><main><span class='tag'>CONFIGURAÇÃO DA VERCEL</span><h1>Faltam variáveis para iniciar o PlannerX</h1>
    <p>Abra o projeto na Vercel, entre em <b>Settings → Environment Variables</b> e conclua:</p><ul>{items}</ul>
    <p>Depois faça um novo <b>Redeploy</b>. O usuário e a senha também podem ser alterados com <code>PLANNERX_USERNAME</code> e <code>PLANNERX_PASSWORD</code>.</p></main></body></html>"""


@app.middleware("http")
async def authentication_middleware(request: Request, call_next):
    path = request.url.path
    if CONFIG_ERRORS and path != "/health" and not path.startswith("/static/"):
        return HTMLResponse(configuration_error_page(), status_code=503)
    public_path = path == "/login" or path.startswith("/static/") or path == "/favicon.ico" or path == "/health"
    if not public_path and not request.session.get("authenticated"):
        if path.startswith("/api/"):
            return JSONResponse({"ok": False, "message": "Sessão encerrada. Faça login novamente."}, status_code=401)
        return RedirectResponse(url="/login", status_code=303)
    return await call_next(request)


app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="ds_plannerx_session",
    same_site="lax",
    https_only=IS_VERCEL,
    max_age=60 * 60 * 12,
)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def asset_url(value: str | None) -> str:
    if not value:
        return ""
    value = str(value)
    if value.startswith(("https://", "http://")):
        return value
    return f"/uploads/{quote(value, safe='')}"


templates.env.filters["asset_url"] = asset_url


class PostgresConnectionAdapter:
    def __init__(self, url: str):
        import psycopg
        from psycopg.rows import dict_row
        self._connection = psycopg.connect(url, row_factory=dict_row)

    @staticmethod
    def _sql(sql: str) -> str:
        return sql.replace("?", "%s")

    def execute(self, sql: str, params: Any = ()):
        return self._connection.execute(self._sql(sql), tuple(params or ()))

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def get_db() -> Any:
    if USE_POSTGRES:
        return PostgresConnectionAdapter(DATABASE_URL)
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_postgres_db() -> None:
    statements = [
        """CREATE TABLE IF NOT EXISTS channels (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            image_path TEXT,
            title_goal INTEGER NOT NULL DEFAULT 12,
            interval_days INTEGER NOT NULL DEFAULT 2,
            frequency_mode TEXT NOT NULL DEFAULT 'interval',
            start_date TEXT NOT NULL,
            planning_month TEXT NOT NULL DEFAULT '',
            calculation_days INTEGER NOT NULL DEFAULT 30,
            period_mode TEXT NOT NULL DEFAULT 'months',
            period_value INTEGER NOT NULL DEFAULT 1,
            daily_script_goal INTEGER NOT NULL DEFAULT 1,
            daily_video_goal INTEGER NOT NULL DEFAULT 1,
            schedule_mode TEXT NOT NULL DEFAULT 'standard',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS videos (
            id BIGSERIAL PRIMARY KEY,
            channel_id BIGINT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'production' CHECK(status IN ('todo', 'production', 'completed')),
            planned_date TEXT,
            description TEXT NOT NULL DEFAULT '',
            cover_image_path TEXT,
            script_completed_at TEXT,
            completed_at TEXT,
            published_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS attachments (
            id BIGSERIAL PRIMARY KEY,
            video_id BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            original_name TEXT NOT NULL,
            stored_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            mime_type TEXT,
            size_bytes BIGINT NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS text_fields (
            id BIGSERIAL PRIMARY KEY,
            video_id BIGINT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
            label TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS channel_titles (
            id BIGSERIAL PRIMARY KEY,
            channel_id BIGINT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            position INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'ready',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(channel_id, position)
        )""",
        """CREATE TABLE IF NOT EXISTS monthly_plans (
            id BIGSERIAL PRIMARY KEY,
            channel_id BIGINT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            year_month TEXT NOT NULL,
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(channel_id, year_month)
        )""",
        """CREATE TABLE IF NOT EXISTS schedule_rules (
            id BIGSERIAL PRIMARY KEY,
            channel_id BIGINT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            year_month TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            frequency_mode TEXT NOT NULL DEFAULT 'interval',
            interval_days INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS production_logs (
            id BIGSERIAL PRIMARY KEY,
            channel_id BIGINT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            history_month TEXT NOT NULL,
            video_title TEXT NOT NULL,
            work_date TEXT NOT NULL,
            operator_name TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )""",
        "CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id)",
        "CREATE INDEX IF NOT EXISTS idx_attachments_video ON attachments(video_id)",
        "CREATE INDEX IF NOT EXISTS idx_text_fields_video ON text_fields(video_id)",
        "CREATE INDEX IF NOT EXISTS idx_monthly_plans_channel ON monthly_plans(channel_id)",
        "CREATE INDEX IF NOT EXISTS idx_schedule_rules_channel_month ON schedule_rules(channel_id, year_month)",
        "CREATE INDEX IF NOT EXISTS idx_production_logs_channel_date ON production_logs(channel_id, work_date)",
        "ALTER TABLE videos ADD COLUMN IF NOT EXISTS cover_image_path TEXT",
        "ALTER TABLE videos ADD COLUMN IF NOT EXISTS script_completed_at TEXT",
        "ALTER TABLE videos ADD COLUMN IF NOT EXISTS completed_at TEXT",
        "ALTER TABLE videos ADD COLUMN IF NOT EXISTS published_at TEXT",
        "ALTER TABLE channels ADD COLUMN IF NOT EXISTS frequency_mode TEXT NOT NULL DEFAULT 'interval'",
        "ALTER TABLE channels ADD COLUMN IF NOT EXISTS planning_month TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE channels ADD COLUMN IF NOT EXISTS calculation_days INTEGER NOT NULL DEFAULT 30",
        "ALTER TABLE channels ADD COLUMN IF NOT EXISTS period_mode TEXT NOT NULL DEFAULT 'months'",
        "ALTER TABLE channels ADD COLUMN IF NOT EXISTS period_value INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE channels ADD COLUMN IF NOT EXISTS daily_script_goal INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE channels ADD COLUMN IF NOT EXISTS daily_video_goal INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE channels ADD COLUMN IF NOT EXISTS schedule_mode TEXT NOT NULL DEFAULT 'standard'",
        "ALTER TABLE channel_titles ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'ready'",
    ]
    with closing(get_db()) as db:
        for statement in statements:
            db.execute(statement)
        db.execute("UPDATE videos SET completed_at = updated_at WHERE status = 'completed' AND completed_at IS NULL")
        db.execute("UPDATE videos SET status = 'production' WHERE status = 'todo'")
        db.execute("UPDATE channels SET daily_script_goal = 1 WHERE daily_script_goal IS NULL OR daily_script_goal < 1")
        db.execute("UPDATE channels SET daily_video_goal = 1 WHERE daily_video_goal IS NULL OR daily_video_goal < 1")
        db.execute("UPDATE channels SET schedule_mode = 'standard' WHERE schedule_mode IS NULL OR schedule_mode NOT IN ('standard', 'custom')")
        db.execute("UPDATE channels SET frequency_mode = 'interval' WHERE frequency_mode IS NULL OR frequency_mode NOT IN ('interval', 'days_off')")
        db.execute("UPDATE channel_titles SET status = 'ready' WHERE status IS NULL OR status NOT IN ('ready', 'progress', 'completed')")
        db.commit()

def init_sqlite_db() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        image_path TEXT,
        title_goal INTEGER NOT NULL DEFAULT 12,
        interval_days INTEGER NOT NULL DEFAULT 2,
        frequency_mode TEXT NOT NULL DEFAULT 'interval',
        start_date TEXT NOT NULL,
        planning_month TEXT NOT NULL DEFAULT '',
        calculation_days INTEGER NOT NULL DEFAULT 30,
        period_mode TEXT NOT NULL DEFAULT 'months',
        period_value INTEGER NOT NULL DEFAULT 1,
        daily_script_goal INTEGER NOT NULL DEFAULT 1,
        daily_video_goal INTEGER NOT NULL DEFAULT 1,
        schedule_mode TEXT NOT NULL DEFAULT 'standard',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'production' CHECK(status IN ('todo', 'production', 'completed')),
        planned_date TEXT,
        description TEXT NOT NULL DEFAULT '',
        cover_image_path TEXT,
        script_completed_at TEXT,
        completed_at TEXT,
        published_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS attachments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL,
        original_name TEXT NOT NULL,
        stored_name TEXT NOT NULL,
        file_type TEXT NOT NULL,
        mime_type TEXT,
        size_bytes INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS text_fields (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER NOT NULL,
        label TEXT NOT NULL,
        content TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS channel_titles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL,
        position INTEGER NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'ready',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE,
        UNIQUE(channel_id, position)
    );

    CREATE TABLE IF NOT EXISTS monthly_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL,
        year_month TEXT NOT NULL,
        notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE,
        UNIQUE(channel_id, year_month)
    );

    CREATE TABLE IF NOT EXISTS schedule_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL,
        year_month TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        frequency_mode TEXT NOT NULL DEFAULT 'interval',
        interval_days INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS production_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL,
        history_month TEXT NOT NULL,
        video_title TEXT NOT NULL,
        work_date TEXT NOT NULL,
        operator_name TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE
    );
    """
    with closing(get_db()) as db:
        db.executescript(schema)
        # Migração automática para versões anteriores: adiciona capa própria aos cards de vídeo.
        video_columns = {row["name"] for row in db.execute("PRAGMA table_info(videos)").fetchall()}
        if "cover_image_path" not in video_columns:
            db.execute("ALTER TABLE videos ADD COLUMN cover_image_path TEXT")
        if "script_completed_at" not in video_columns:
            db.execute("ALTER TABLE videos ADD COLUMN script_completed_at TEXT")
        if "completed_at" not in video_columns:
            db.execute("ALTER TABLE videos ADD COLUMN completed_at TEXT")
            # Preserva uma data aproximada para cards que já estavam concluídos.
            db.execute("UPDATE videos SET completed_at = updated_at WHERE status = 'completed' AND completed_at IS NULL")
        if "published_at" not in video_columns:
            db.execute("ALTER TABLE videos ADD COLUMN published_at TEXT")

        # v2.0: o modo visual "Pra fazer" foi removido.
        db.execute("UPDATE videos SET status = 'production' WHERE status = 'todo'")

        channel_columns = {row["name"] for row in db.execute("PRAGMA table_info(channels)").fetchall()}
        if "frequency_mode" not in channel_columns:
            db.execute("ALTER TABLE channels ADD COLUMN frequency_mode TEXT NOT NULL DEFAULT 'interval'")
        if "planning_month" not in channel_columns:
            db.execute("ALTER TABLE channels ADD COLUMN planning_month TEXT NOT NULL DEFAULT ''")
        if "calculation_days" not in channel_columns:
            db.execute("ALTER TABLE channels ADD COLUMN calculation_days INTEGER NOT NULL DEFAULT 30")
        if "daily_script_goal" not in channel_columns:
            db.execute("ALTER TABLE channels ADD COLUMN daily_script_goal INTEGER NOT NULL DEFAULT 1")
        if "daily_video_goal" not in channel_columns:
            db.execute("ALTER TABLE channels ADD COLUMN daily_video_goal INTEGER NOT NULL DEFAULT 1")
        if "schedule_mode" not in channel_columns:
            db.execute("ALTER TABLE channels ADD COLUMN schedule_mode TEXT NOT NULL DEFAULT 'standard'")
        db.execute("UPDATE channels SET daily_script_goal = 1 WHERE daily_script_goal IS NULL OR daily_script_goal < 1")
        db.execute("UPDATE channels SET daily_video_goal = 1 WHERE daily_video_goal IS NULL OR daily_video_goal < 1")
        had_period_mode = "period_mode" in channel_columns
        had_period_value = "period_value" in channel_columns
        if not had_period_mode:
            db.execute("ALTER TABLE channels ADD COLUMN period_mode TEXT NOT NULL DEFAULT 'months'")
        if not had_period_value:
            db.execute("ALTER TABLE channels ADD COLUMN period_value INTEGER NOT NULL DEFAULT 1")
        db.execute(
            "UPDATE channels SET frequency_mode = 'interval' "
            "WHERE frequency_mode IS NULL OR frequency_mode NOT IN ('interval', 'days_off')"
        )

        # Migração v1.8: etiquetas independentes de status no Banco de Títulos.
        # Elas servem somente para consulta visual e não alteram metas, progresso
        # da produção, contadores de vídeos ou o preenchimento do banco.
        title_columns = {row["name"] for row in db.execute("PRAGMA table_info(channel_titles)").fetchall()}
        if "status" not in title_columns:
            db.execute("ALTER TABLE channel_titles ADD COLUMN status TEXT NOT NULL DEFAULT 'ready'")
        db.execute(
            "UPDATE channel_titles SET status = 'ready' "
            "WHERE status IS NULL OR status NOT IN ('ready', 'progress', 'completed')"
        )

        # Migração para o novo período explícito. A versão anterior misturava
        # "mês final" com "quantidade de dias", o que fazia 1 mês virar 30 dias.
        rows = db.execute(
            "SELECT id, start_date, planning_month, calculation_days, period_mode, period_value FROM channels"
        ).fetchall()
        for row in rows:
            start = parse_iso_date(row["start_date"])
            planning_month = str(row["planning_month"] or "").strip()
            current_days = max(1, int(row["calculation_days"] or 30))
            mode = str(row["period_mode"] or "").strip()
            value = max(1, int(row["period_value"] or 1))

            if not had_period_mode or not had_period_value or mode not in PERIOD_MODES:
                # Ciclo antigo de 30 dias começando no mesmo mês: converte para
                # 1 mês de calendário, preservando a intenção do usuário.
                if current_days == 30 and (not planning_month or planning_month == start.strftime("%Y-%m")):
                    mode, value = "months", 1
                elif planning_month and current_days == days_until_month_end(start, planning_month):
                    mode, value = "month_end", 1
                else:
                    mode, value = "days", current_days

            projection = calculate_period(start, mode, value, planning_month)
            db.execute(
                """UPDATE channels SET planning_month = ?, calculation_days = ?,
                period_mode = ?, period_value = ? WHERE id = ?""",
                (
                    projection["planning_month"], projection["period_days"],
                    projection["period_mode"], projection["period_value"], row["id"],
                ),
            )
        db.commit()




def init_db() -> None:
    if CONFIG_ERRORS and IS_VERCEL:
        return
    if USE_POSTGRES:
        init_postgres_db()
    else:
        init_sqlite_db()


def local_now() -> datetime:
    return datetime.now(APP_TIMEZONE)


def today_local() -> date:
    return local_now().date()


def now_iso() -> str:
    return local_now().replace(tzinfo=None, microsecond=0).isoformat(sep=" ")


def parse_iso_date(value: str | None, fallback: date | None = None) -> date:
    if value:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            pass
    return fallback or today_local()


def parse_year_month(value: str | None, fallback: date | None = None) -> tuple[int, int]:
    if value:
        try:
            parsed = datetime.strptime(value, "%Y-%m")
            return parsed.year, parsed.month
        except ValueError:
            pass
    base = fallback or today_local()
    return base.year, base.month


def month_end_date(value: str | None, fallback: date | None = None) -> date:
    year, month = parse_year_month(value, fallback)
    return date(year, month, calendar.monthrange(year, month)[1])


def normalize_planning_month(value: str | None, start: date) -> str:
    year, month = parse_year_month(value, start)
    end = date(year, month, calendar.monthrange(year, month)[1])
    if end < start:
        return start.strftime("%Y-%m")
    return f"{year:04d}-{month:02d}"


def days_until_month_end(start: date, planning_month: str | None) -> int:
    normalized = normalize_planning_month(planning_month, start)
    return max(1, (month_end_date(normalized, start) - start).days + 1)


def normalize_calculation_days(value: int | str | None, default: int) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        parsed = 0
    return min(max(parsed or default, 1), 7300)


def normalize_period_mode(value: str | None) -> str:
    return value if value in PERIOD_MODES else "months"


def normalize_period_value(value: int | str | None, mode: str) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        parsed = 0
    if mode == "months":
        return min(max(parsed or 1, 1), 120)
    if mode == "days":
        return min(max(parsed or 30, 1), 7300)
    return 1


def add_calendar_months(start: date, months: int) -> date:
    """Soma meses de calendário preservando o dia quando ele existe.

    Ex.: 27/07/2026 + 1 mês = 27/08/2026. Para datas no fim do mês,
    o dia é limitado ao último dia do mês de destino.
    """
    months = max(1, int(months or 1))
    month_index = (start.month - 1) + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def calculate_period(
    start: date,
    period_mode: str | None,
    period_value: int | str | None,
    planning_month: str | None,
) -> dict[str, Any]:
    mode = normalize_period_mode(period_mode)
    value = normalize_period_value(period_value, mode)

    if mode == "months":
        end = add_calendar_months(start, value)
        normalized_month = end.strftime("%Y-%m")
        summary = f"{value} mês{'es' if value != 1 else ''} completo{'s' if value != 1 else ''}"
    elif mode == "days":
        end = start + timedelta(days=value - 1)
        normalized_month = end.strftime("%Y-%m")
        summary = f"{value} dias exatos"
    else:
        normalized_month = normalize_planning_month(planning_month, start)
        end = month_end_date(normalized_month, start)
        if end < start:
            normalized_month = start.strftime("%Y-%m")
            end = month_end_date(normalized_month, start)
        summary = f"até o fim de {planning_month_text(normalized_month, start).lower()}"

    period_days = (end - start).days + 1
    return {
        "period_mode": mode,
        "period_value": value,
        "period_start": start,
        "period_end": end,
        "period_days": max(1, period_days),
        "planning_month": normalized_month,
        "planning_month_text": planning_month_text(normalized_month, start),
        "period_summary": summary,
    }


def planning_month_text(value: str | None, fallback: date) -> str:
    year, month = parse_year_month(value, fallback)
    return f"{MONTH_NAMES_PT[month]} de {year}"


def safe_filename(filename: str) -> str:
    cleaned = "".join(char for char in filename if char.isalnum() or char in "._- ()[]").strip()
    return cleaned or "arquivo"


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def detect_file_type(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in {"mp4", "mov", "mkv", "avi", "webm", "m4v"}:
        return "video"
    if ext in {"mp3", "wav", "m4a", "aac", "ogg", "flac"}:
        return "audio"
    if ext in {"png", "jpg", "jpeg", "webp", "gif", "svg"}:
        return "image"
    if ext == "pdf":
        return "pdf"
    return "text"


def save_upload(upload: UploadFile) -> tuple[str, str, str, str | None, int]:
    if IS_VERCEL:
        raise ValueError(
            "O upload em nuvem não foi iniciado. Atualize a página e tente novamente com o JavaScript ativado."
        )
    original = safe_filename(upload.filename or "arquivo")
    if not allowed_file(original):
        raise ValueError(f"Formato não permitido: {upload.filename}")
    ext = original.rsplit(".", 1)[1].lower()
    stored = f"{uuid.uuid4().hex}.{ext}"
    destination = UPLOAD_DIR / stored
    upload.file.seek(0)
    with destination.open("wb") as target:
        shutil.copyfileobj(upload.file, target, length=1024 * 1024)
    mime = upload.content_type or mimetypes.guess_type(original)[0]
    return original, stored, detect_file_type(original), mime, destination.stat().st_size


def is_vercel_blob_url(value: str | None) -> bool:
    if not value:
        return False
    try:
        parsed = urlparse(str(value))
    except ValueError:
        return False
    return parsed.scheme == "https" and parsed.hostname is not None and parsed.hostname.endswith("blob.vercel-storage.com")


def validate_cloud_upload(
    stored_url: str, original_name: str, mime_type: str | None, size_bytes: int | str | None,
) -> tuple[str, str, str, str | None, int]:
    original = safe_filename(original_name or "arquivo")
    if not allowed_file(original):
        raise ValueError(f"Formato não permitido: {original_name}")
    if not is_vercel_blob_url(stored_url):
        raise ValueError("O arquivo enviado não pertence ao armazenamento autorizado do PlannerX.")
    try:
        parsed_size = max(0, int(size_bytes or 0))
    except (TypeError, ValueError):
        parsed_size = 0
    mime = (mime_type or mimetypes.guess_type(original)[0] or "application/octet-stream").strip()
    return original, stored_url.strip(), detect_file_type(original), mime, parsed_size


def remove_upload(filename: str | None) -> None:
    if not filename:
        return
    if is_vercel_blob_url(filename):
        if not (BLOB_ENABLED and IS_VERCEL):
            return
        try:
            from urllib.request import Request as UrlRequest, urlopen

            deployment_host = (
                os.environ.get("VERCEL_PROJECT_PRODUCTION_URL")
                or os.environ.get("VERCEL_URL")
                or ""
            ).strip().removeprefix("https://").removeprefix("http://").rstrip("/")
            if not deployment_host:
                return
            payload = json.dumps({
                "auth": make_upload_auth_token(120),
                "url": filename,
            }).encode("utf-8")
            request = UrlRequest(
                f"https://{deployment_host}/api/blob-delete",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=8):
                pass
        except Exception:
            # O registro é removido mesmo se o provedor estiver temporariamente
            # indisponível; a exclusão física pode ser refeita pelo painel Blob.
            pass
        return
    path = UPLOAD_DIR / filename
    if path.exists() and path.is_file():
        path.unlink(missing_ok=True)


def make_upload_auth_token(valid_for_seconds: int = 600) -> str:
    expires_at = int(time.time()) + max(60, valid_for_seconds)
    message = str(expires_at).encode("utf-8")
    signature = hmac.new(SESSION_SECRET.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return f"{expires_at}.{signature}"


def normalize_frequency_mode(value: str | None) -> str:
    return value if value in FREQUENCY_MODES else "interval"


def normalize_frequency_value(value: int | str | None, mode: str) -> int:
    try:
        parsed = int(value or 0)
    except (TypeError, ValueError):
        parsed = 0
    return max(0, parsed) if mode == "days_off" else max(1, parsed)


def effective_interval_days(value: int | str | None, mode: str | None) -> int:
    normalized_mode = normalize_frequency_mode(mode)
    normalized_value = normalize_frequency_value(value, normalized_mode)
    # No modo "dias sem postar", os dias de pausa ficam entre duas publicações.
    # Ex.: postagem dia 27 + 2 dias completos sem postar = nova postagem dia 30.
    return normalized_value + 1 if normalized_mode == "days_off" else normalized_value


def frequency_text(value: int | str | None, mode: str | None, compact: bool = False) -> str:
    normalized_mode = normalize_frequency_mode(mode)
    normalized_value = normalize_frequency_value(value, normalized_mode)
    if normalized_mode == "days_off":
        if normalized_value == 0:
            return "todos os dias"
        unit = "dia" if normalized_value == 1 else "dias"
        return f"{normalized_value} {unit} sem postar"
    if normalized_value == 1:
        return "todos os dias"
    unit = "dia" if normalized_value == 1 else "dias"
    text = f"a cada {normalized_value} {unit}"
    if normalized_value == 2 and not compact:
        text += " · dia sim, dia não"
    return text


def schedule_dates(start: date, step_days: int, period_days: int) -> list[date]:
    step_days = max(1, int(step_days or 1))
    period_days = max(1, int(period_days or 1))
    end = start + timedelta(days=period_days - 1)
    dates: list[date] = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=step_days)
    return dates


def month_projection(
    start: date,
    interval_days: int,
    frequency_mode: str = "interval",
    period_mode: str = "months",
    period_value: int | str | None = 1,
    planning_month: str | None = None,
    calculation_days: int | str | None = None,
) -> dict[str, Any]:
    """Calcula as postagens usando um período sem ambiguidades.

    - ``months``: soma meses de calendário. 27/07 + 1 mês = 27/08.
    - ``days``: usa exatamente a quantidade de dias, incluindo a data inicial.
    - ``month_end``: segue até o último dia do mês escolhido.

    A frequência também permanece explícita:
    - intervalo 2: 27, 29, 31...;
    - 2 dias completos sem postar: 27, 30, 02....
    """
    mode = normalize_frequency_mode(frequency_mode)
    value = normalize_frequency_value(interval_days, mode)
    step_days = effective_interval_days(value, mode)

    # Compatibilidade defensiva com bancos antigos que ainda não têm os novos campos.
    normalized_period_mode = normalize_period_mode(period_mode)
    normalized_period_value = normalize_period_value(period_value, normalized_period_mode)
    period = calculate_period(start, normalized_period_mode, normalized_period_value, planning_month)
    if normalized_period_mode == "days" and calculation_days not in (None, ""):
        fallback_days = normalize_calculation_days(calculation_days, period["period_days"])
        if normalized_period_value <= 0:
            period = calculate_period(start, "days", fallback_days, planning_month)

    dates = schedule_dates(start, step_days, period["period_days"])
    if mode == "days_off":
        if value == 0:
            formula = f"{period['period_days']} dias · postagem diária"
        else:
            formula = (
                f"{period['period_days']} dias · ciclo de {step_days} dias "
                f"(1 postagem + {value} dia{'s' if value != 1 else ''} sem postar)"
            )
    else:
        formula = (
            f"{period['period_days']} dias · intervalo de {step_days} "
            f"dia{'s' if step_days != 1 else ''} entre as postagens"
        )

    return {
        "count": len(dates),
        "dates": dates,
        **period,
        "frequency_mode": mode,
        "frequency_value": value,
        "step_days": step_days,
        "frequency_text": frequency_text(value, mode),
        "frequency_text_compact": frequency_text(value, mode, compact=True),
        "period_label": f"{start.strftime('%d/%m/%Y')} até {period['period_end'].strftime('%d/%m/%Y')}",
        "formula_text": formula,
    }



def normalize_schedule_mode(value: str | None) -> str:
    return value if value in SCHEDULE_MODES else "standard"


def valid_year_month(value: str | None, fallback: date | None = None) -> str:
    base = fallback or today_local()
    try:
        parsed = datetime.strptime(str(value or ""), "%Y-%m")
        return parsed.strftime("%Y-%m")
    except ValueError:
        return base.strftime("%Y-%m")


def custom_schedule_dates(db: Any, channel_id: int, year_month: str | None = None) -> list[date]:
    sql = "SELECT * FROM schedule_rules WHERE channel_id = ?"
    params: list[Any] = [channel_id]
    if year_month:
        sql += " AND year_month = ?"
        params.append(valid_year_month(year_month))
    sql += " ORDER BY start_date, id"
    rules = db.execute(sql, params).fetchall()
    all_dates: set[date] = set()
    for rule in rules:
        start = parse_iso_date(rule["start_date"])
        end = parse_iso_date(rule["end_date"], start)
        if end < start:
            start, end = end, start
        mode = normalize_frequency_mode(rule["frequency_mode"])
        value = normalize_frequency_value(rule["interval_days"], mode)
        step = effective_interval_days(value, mode)
        current = start
        while current <= end:
            all_dates.add(current)
            current += timedelta(days=max(1, step))
    return sorted(all_dates)


def channel_projection(db: Any, channel: Any) -> dict[str, Any]:
    schedule_mode = normalize_schedule_mode(channel["schedule_mode"] if "schedule_mode" in channel.keys() else "standard")
    if schedule_mode != "custom":
        return month_projection(
            parse_iso_date(channel["start_date"]),
            channel["interval_days"], channel["frequency_mode"], channel["period_mode"],
            channel["period_value"], channel["planning_month"], channel["calculation_days"],
        ) | {"schedule_mode": "standard"}

    dates = custom_schedule_dates(db, int(channel["id"]))
    if dates:
        start, end = dates[0], dates[-1]
        period_days = (end - start).days + 1
        period_label = f"{start.strftime('%d/%m/%Y')} até {end.strftime('%d/%m/%Y')}"
        planning_month = end.strftime("%Y-%m")
    else:
        start = parse_iso_date(channel["start_date"])
        end = start
        period_days = 1
        period_label = "Crie regras nos meses do calendário"
        planning_month = start.strftime("%Y-%m")
    return {
        "count": len(dates),
        "dates": dates,
        "period_start": start,
        "period_end": end,
        "period_days": period_days,
        "planning_month": planning_month,
        "planning_month_text": planning_month_text(planning_month, start),
        "period_summary": "planejamento personalizado",
        "period_label": period_label,
        "formula_text": f"União das regras mensais, sem repetir datas ({len(dates)} datas)",
        "frequency_mode": "custom",
        "frequency_value": 0,
        "step_days": 0,
        "frequency_text": "personalizado por mês",
        "frequency_text_compact": "ritmo personalizado",
        "schedule_mode": "custom",
    }


def schedule_date_items(db: Any, channel_id: int, dates: list[date]) -> list[dict[str, Any]]:
    rows = db.execute(
        "SELECT id, title, planned_date, published_at FROM videos WHERE channel_id = ? AND planned_date IS NOT NULL",
        (channel_id,),
    ).fetchall()
    by_date: dict[str, list[Any]] = {}
    for row in rows:
        by_date.setdefault(str(row["planned_date"]), []).append(row)
    today = today_local()
    items: list[dict[str, Any]] = []
    for item_date in dates:
        key = item_date.isoformat()
        linked = by_date.get(key, [])
        published_count = sum(1 for video in linked if video["published_at"])
        if linked and published_count == len(linked):
            state, label = "published", "Publicado"
        elif item_date == today:
            state, label = "today", "Postagem de hoje"
        elif item_date < today:
            state, label = "overdue", "Não publicado"
        else:
            state, label = "future", "Postagem prevista"
        items.append({
            "date": item_date,
            "state": state,
            "label": label,
            "videos": linked,
            "published_count": published_count,
        })
    return items


def month_calendar(db: Any, channel_id: int, year: int) -> list[dict[str, Any]]:
    plans = db.execute(
        "SELECT year_month, notes FROM monthly_plans WHERE channel_id = ? AND year_month LIKE ?",
        (channel_id, f"{year:04d}-%"),
    ).fetchall()
    plan_map = {row["year_month"]: row for row in plans}
    result = []
    for month in range(1, 13):
        key = f"{year:04d}-{month:02d}"
        video_row = db.execute(
            "SELECT COUNT(*) AS total FROM videos WHERE channel_id = ? AND planned_date LIKE ?",
            (channel_id, f"{key}-%"),
        ).fetchone()
        rule_row = db.execute(
            "SELECT COUNT(*) AS total FROM schedule_rules WHERE channel_id = ? AND year_month = ?",
            (channel_id, key),
        ).fetchone()
        total_videos = int(video_row["total"] or 0)
        total_rules = int(rule_row["total"] or 0)
        result.append({
            "year_month": key,
            "short": MONTH_NAMES_PT[month][:3].upper(),
            "name": MONTH_NAMES_PT[month],
            "month": month,
            "has_plan": key in plan_map or total_rules > 0 or total_videos > 0,
            "video_count": total_videos,
            "rule_count": total_rules,
            "is_current": year == today_local().year and month == today_local().month,
        })
    return result


CELEBRATION_MESSAGES = {
    "script": [
        "Meta de roteiros alcançada! A página em branco pediu demissão. 👑",
        "Roteiros do dia garantidos. O café pode solicitar participação nos lucros.",
        "Meta de roteiros batida! Hoje a criatividade trabalhou sem reclamar do horário.",
    ],
    "video": [
        "Meta de vídeos alcançada! O botão publicar já está chamando você de chefe.",
        "Vídeos do dia concluídos. O algoritmo foi avisado para se comportar.",
        "Meta de vídeos batida! A timeline ficou tão organizada que parece montagem.",
    ],
    "both": [
        "Dupla meta alcançada! Roteiros e vídeos concluídos antes da procrastinação abrir o expediente.",
        "Meta dupla no bolso! Hoje até a lista de tarefas ficou sem resposta.",
        "Roteiros e vídeos: missão cumprida. Pode erguer o troféu sem modéstia.",
    ],
    "general": [
        "Meta geral alcançada! O PlannerX oficialmente ficou pequeno para esse ritmo.",
        "100% concluído! A barra de progresso agora está exigindo tapete vermelho.",
        "Meta geral vencida. O algoritmo recebeu o comunicado e a procrastinação perdeu o crachá.",
    ],
}


def celebration_payload(kind: str | None) -> dict[str, str] | None:
    if kind not in CELEBRATION_MESSAGES:
        return None
    messages = CELEBRATION_MESSAGES[kind]
    index = (today_local().toordinal() + int(time.time())) % len(messages)
    return {"kind": kind, "title": "META ALCANÇADA", "message": messages[index], "emoji": "🏆"}


def achieved_kind(before: dict[str, Any], after: dict[str, Any], general_before: bool = False, general_after: bool = False) -> str | None:
    if not general_before and general_after:
        return "general"
    script_new = not bool(before.get("scripts_complete")) and bool(after.get("scripts_complete"))
    video_new = not bool(before.get("videos_complete")) and bool(after.get("videos_complete"))
    if script_new and video_new:
        return "both"
    if script_new:
        return "script"
    if video_new:
        return "video"
    return None


def channel_stats(db: sqlite3.Connection, channel_id: int, title_goal: int) -> dict[str, int | float]:
    rows = db.execute(
        "SELECT status, COUNT(*) AS total FROM videos WHERE channel_id = ? GROUP BY status",
        (channel_id,),
    ).fetchall()
    counts = {"todo": 0, "production": 0, "completed": 0}
    for row in rows:
        counts[row["status"]] = row["total"]
    total = sum(counts.values())
    goal = max(1, int(title_goal or 1))
    title_row = db.execute(
        "SELECT COUNT(*) AS total FROM channel_titles WHERE channel_id = ? AND TRIM(title) <> ''",
        (channel_id,),
    ).fetchone()
    title_count = int(title_row["total"] if title_row else 0)

    # Indicadores independentes:
    # - Títulos restantes acompanha somente a produção concluída.
    # - Banco de títulos acompanha somente os campos preenchidos no banco.
    remaining_titles = max(goal - counts["completed"], 0)
    bank_remaining_titles = max(goal - title_count, 0)
    progress = min(counts["completed"] / goal * 100, 100)
    title_progress = min(title_count / goal * 100, 100)
    return {
        **counts,
        "total": total,
        "goal": goal,
        "title_count": title_count,
        "remaining_titles": remaining_titles,
        "bank_remaining_titles": bank_remaining_titles,
        "progress": round(progress, 1),
        "title_progress": round(title_progress, 1),
    }



def daily_goal_stats(db: Any, channel: Any, target_date: date | None = None) -> dict[str, int | float | str]:
    """Soma ações dos cards e lançamentos manuais do Fluxo de Produção."""
    selected = target_date or today_local()
    selected_iso = selected.isoformat()
    card_row = db.execute(
        """SELECT
            SUM(CASE WHEN DATE(script_completed_at) = ? THEN 1 ELSE 0 END) AS scripts_done,
            SUM(CASE WHEN DATE(completed_at) = ? THEN 1 ELSE 0 END) AS videos_done
        FROM videos WHERE channel_id = ?""",
        (selected_iso, selected_iso, channel["id"]),
    ).fetchone()
    log_row = db.execute(
        """SELECT
            SUM(CASE WHEN status = 'script_ready' THEN 1 ELSE 0 END) AS scripts_done,
            SUM(CASE WHEN status = 'video_completed' THEN 1 ELSE 0 END) AS videos_done
        FROM production_logs WHERE channel_id = ? AND work_date = ?""",
        (channel["id"], selected_iso),
    ).fetchone()
    script_goal = max(1, int(channel["daily_script_goal"] or 1))
    video_goal = max(1, int(channel["daily_video_goal"] or 1))
    scripts_done = int(card_row["scripts_done"] or 0) + int(log_row["scripts_done"] or 0)
    videos_done = int(card_row["videos_done"] or 0) + int(log_row["videos_done"] or 0)
    return {
        "date": selected_iso,
        "date_br": selected.strftime("%d/%m/%Y"),
        "script_goal": script_goal,
        "video_goal": video_goal,
        "scripts_done": scripts_done,
        "videos_done": videos_done,
        "script_progress": min(round(scripts_done / script_goal * 100, 1), 100),
        "video_progress": min(round(videos_done / video_goal * 100, 1), 100),
        "scripts_complete": scripts_done >= script_goal,
        "videos_complete": videos_done >= video_goal,
    }


def channel_motivation(
    channel_id: int,
    stats: dict[str, int | float],
    daily_stats: dict[str, int | float | str],
    login_message: str | None = None,
) -> dict[str, str]:
    """Frase dinâmica por login, andamento diário e metas alcançadas."""
    completed = int(stats.get("completed", 0) or 0)
    goal = max(1, int(stats.get("goal", 1) or 1))
    remaining = max(goal - completed, 0)
    progress = float(stats.get("progress", 0) or 0)
    scripts_done = int(daily_stats.get("scripts_done", 0) or 0)
    videos_done = int(daily_stats.get("videos_done", 0) or 0)
    script_goal = max(1, int(daily_stats.get("script_goal", 1) or 1))
    video_goal = max(1, int(daily_stats.get("video_goal", 1) or 1))
    scripts_complete = bool(daily_stats.get("scripts_complete"))
    videos_complete = bool(daily_stats.get("videos_complete"))

    if login_message:
        return {"emoji": "🔐", "label": "MENSAGEM DO LOGIN", "text": login_message}
    if completed >= goal:
        label, emoji = "META GERAL BATIDA", "🏆"
        messages = [
            f"{completed} de {goal}! A meta geral foi concluída e a barra de progresso agora está se achando celebridade.",
            "Meta geral vencida. O algoritmo recebeu o recado e a procrastinação pediu transferência.",
            "100% concluído! Pode comemorar: hoje até a lista de tarefas ficou sem argumento.",
        ]
    elif scripts_complete and videos_complete:
        label, emoji = "DUPLA META DO DIA", "🥇"
        messages = [
            f"Roteiros {scripts_done}/{script_goal} e vídeos {videos_done}/{video_goal}. Duas metas no bolso e ainda sobrou elegância.",
            "Meta de roteiros e vídeos concluída hoje. A produtividade veio trabalhar de roupa social.",
            "Dobradinha completa! Roteiros e vídeos bateram a meta antes que a procrastinação inventasse uma desculpa nova.",
        ]
    elif scripts_complete:
        label, emoji = "META DE ROTEIROS BATIDA", "📜"
        messages = [
            f"{scripts_done}/{script_goal} roteiros hoje. A página em branco perdeu oficialmente a discussão.",
            "Meta diária de roteiros concluída! As ideias fizeram fila e, pela primeira vez, ninguém furou.",
            "Roteiros do dia garantidos. Agora o cursor pode descansar sem culpa por alguns segundos.",
        ]
    elif videos_complete:
        label, emoji = "META DE VÍDEOS BATIDA", "🎬"
        messages = [
            f"{videos_done}/{video_goal} vídeos concluídos hoje. O botão Publicar já sabe quem manda.",
            "Meta diária de vídeos batida! A timeline ficou tão organizada que até assustou.",
            "Vídeos do dia concluídos. O algoritmo pode preparar a recepção.",
        ]
    elif scripts_done or videos_done:
        label, emoji = "RITMO DO DIA", "⚡"
        messages = [
            f"Hoje já temos {scripts_done}/{script_goal} roteiros e {videos_done}/{video_goal} vídeos. A máquina ligou; não encoste no fio.",
            "As metas diárias começaram a andar. Continue antes que elas percebam que poderiam correr.",
            "Produção em movimento: um clique por vez e a desculpa do ‘depois eu faço’ vai ficando desempregada.",
        ]
    elif progress < 25:
        label, emoji = "EMPURRÃOZINHO DO DIA", "☕"
        messages = [
            "A meta está no aquecimento — o café já fez a parte dele, agora falta o próximo vídeo.",
            "O painel está calmo demais. Abra um card antes que ele comece a tirar férias.",
            "Um vídeo concluído vale mais que quarenta e sete abas abertas com boas intenções.",
        ]
    elif progress < 50:
        label, emoji = "RITMO PEGANDO", "🚀"
        messages = [
            f"{completed} concluídos. A procrastinação acaba de perder mais um round.",
            f"Faltam {remaining}. A engrenagem pegou e já está fazendo pose para a foto.",
            "A meta começou a ficar com medo de você. Continue assim.",
        ]
    elif progress < 75:
        label, emoji = "PASSOU DA METADE", "😎"
        messages = [
            "Passou da metade! Desistir agora dá mais trabalho do que terminar.",
            f"{completed} concluídos e só {remaining} pela frente. A barra já está se achando importante.",
            "Metade vencida. O botão Publicar já começou a respeitar seu nome.",
        ]
    else:
        label, emoji = "RETA FINAL", "🔥"
        messages = [
            f"Só faltam {remaining}. A meta tentou se esconder, mas a barra de progresso entregou tudo.",
            "Reta final! Organizar pastas não conta como vídeo, então vamos ao que interessa.",
            f"{completed} concluídos. Agora é só não deixar a última etapa inventar personalidade.",
        ]
    index = (today_local().toordinal() + channel_id + completed + scripts_done + videos_done) % len(messages)
    return {"emoji": emoji, "label": label, "text": messages[index]}


def get_channel_or_404(db: sqlite3.Connection, channel_id: int) -> sqlite3.Row:
    channel = db.execute("SELECT * FROM channels WHERE id = ?", (channel_id,)).fetchone()
    if channel is None:
        raise HTTPException(status_code=404, detail="Canal não encontrado")
    return channel


def get_video_or_404(db: sqlite3.Connection, video_id: int) -> sqlite3.Row:
    video = db.execute(
        """SELECT videos.*, channels.name AS channel_name
        FROM videos JOIN channels ON channels.id = videos.channel_id
        WHERE videos.id = ?""",
        (video_id,),
    ).fetchone()
    if video is None:
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")
    return video


def redirect_to(path: str, message: str | None = None, kind: str = "success") -> RedirectResponse:
    if message:
        separator = "&" if "?" in path else "?"
        path = f"{path}{separator}msg={quote(message)}&kind={quote(kind)}"
    return RedirectResponse(path, status_code=303)


def template_context(request: Request, **kwargs: Any) -> dict[str, Any]:
    message = request.query_params.get("msg")
    messages = [(request.query_params.get("kind", "success"), message)] if message else []
    route = request.scope.get("route")
    active_endpoint = getattr(route, "name", "")
    return {
        "request": request,
        "status_labels": STATUS_LABELS,
        "frequency_modes": FREQUENCY_MODES,
        "period_modes": PERIOD_MODES,
        "schedule_modes": SCHEDULE_MODES,
        "today": today_local().isoformat(),
        "default_period_mode": "months",
        "default_period_value": 1,
        "default_planning_month": add_calendar_months(today_local(), 1).strftime("%Y-%m"),
        "messages": messages,
        "active_endpoint": active_endpoint,
        "current_user": request.session.get("username", ""),
        "cloud_upload_enabled": CLOUD_UPLOAD_ENABLED,
        "celebration": celebration_payload(request.query_params.get("celebrate")),
        **kwargs,
    }


def date_br(value: str | date | None) -> str:
    if not value:
        return "—"
    try:
        parsed = value if isinstance(value, date) else datetime.strptime(str(value), "%Y-%m-%d").date()
        return parsed.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(value)


def filesize(value: int | None) -> str:
    size = float(value or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


templates.env.filters["date_br"] = date_br
templates.env.filters["filesize"] = filesize




@app.get("/health", name="health")
def health():
    return {
        "ok": not CONFIG_ERRORS,
        "database": "postgres" if USE_POSTGRES else "sqlite",
        "storage": "vercel-blob" if BLOB_ENABLED else "local",
        "version": "2.3-vercel",
    }


@app.get("/api/blob-upload-auth", name="blob_upload_auth")
def blob_upload_auth():
    if not BLOB_ENABLED:
        return JSONResponse({"ok": False, "message": "Vercel Blob ainda não foi configurado."}, status_code=503)
    return {"ok": True, "token": make_upload_auth_token(), "expires_in": 600}


@app.get("/login", response_class=HTMLResponse, name="login")
def login_page(request: Request):
    if request.session.get("authenticated"):
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"request": request, "error": None})


@app.post("/login", response_class=HTMLResponse, name="login_submit")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    valid_user = hmac.compare_digest(username.strip(), LOGIN_USERNAME)
    if not (valid_user and password_matches(password)):
        return templates.TemplateResponse(
            request, "login.html",
            {"request": request, "error": "Usuário ou senha incorretos.", "username": username.strip()},
            status_code=401,
        )
    request.session.clear()
    request.session["authenticated"] = True
    request.session["username"] = LOGIN_USERNAME
    request.session["login_at"] = now_iso()
    return redirect_to("/", "Acesso liberado. Bem-vinda ao DS - PLANNERX.")


@app.post("/logout", name="logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@app.get("/", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request):
    with closing(get_db()) as db:
        channels = db.execute("SELECT * FROM channels ORDER BY updated_at DESC").fetchall()
        cards = []
        aggregate = {"channels": len(channels), "production": 0, "completed": 0, "total": 0}
        for channel in channels:
            stats = channel_stats(db, channel["id"], channel["title_goal"])
            projection = channel_projection(db, channel)
            cards.append({"channel": channel, "stats": stats, "projection": projection})
            for key in ("production", "completed", "total"):
                aggregate[key] += int(stats[key])
    return templates.TemplateResponse(request, "dashboard.html", template_context(request, cards=cards, aggregate=aggregate))


@app.post("/channels", name="create_channel")
def create_channel(
    name: str = Form(...), description: str = Form(""), title_goal: int = Form(12),
    interval_days: int = Form(2), frequency_mode: str = Form("interval"),
    schedule_mode: str = Form("standard"), start_date: str = Form(...), period_mode: str = Form("months"),
    period_value: str = Form("1"), planning_month: str = Form(""),
    calculation_days: str = Form(""), image: UploadFile | None = File(None),
    image_cloud_url: str = Form(""), image_cloud_name: str = Form(""),
    image_cloud_mime: str = Form(""), image_cloud_size: str = Form(""),
):
    name = name.strip()
    if not name:
        return redirect_to("/", "Informe o nome do canal.", "error")
    image_path = None
    if image_cloud_url:
        try:
            _, image_path, file_type, _, _ = validate_cloud_upload(
                image_cloud_url, image_cloud_name, image_cloud_mime, image_cloud_size,
            )
            if file_type != "image":
                remove_upload(image_path)
                raise ValueError("A capa do canal precisa ser uma imagem.")
        except ValueError as exc:
            remove_upload(image_cloud_url)
            return redirect_to("/", str(exc), "error")
    elif image and image.filename:
        try:
            _, image_path, file_type, _, _ = save_upload(image)
            if file_type != "image":
                remove_upload(image_path)
                raise ValueError("A capa do canal precisa ser uma imagem.")
        except ValueError as exc:
            return redirect_to("/", str(exc), "error")
    timestamp = now_iso()
    mode = normalize_frequency_mode(frequency_mode)
    frequency_value = normalize_frequency_value(interval_days, mode)
    parsed_start = parse_iso_date(start_date)
    normalized_period_mode = normalize_period_mode(period_mode)
    normalized_period_value = normalize_period_value(period_value, normalized_period_mode)
    period = calculate_period(parsed_start, normalized_period_mode, normalized_period_value, planning_month)
    insert_sql = """INSERT INTO channels (
        name, description, image_path, title_goal, interval_days, frequency_mode,
        start_date, planning_month, calculation_days, period_mode, period_value, schedule_mode,
        created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    if USE_POSTGRES:
        insert_sql += " RETURNING id"
    with closing(get_db()) as db:
        cursor = db.execute(
            insert_sql,
            (
                name, description.strip(), image_path, max(1, title_goal), frequency_value, mode,
                parsed_start.isoformat(), period["planning_month"], period["period_days"],
                period["period_mode"], period["period_value"], normalize_schedule_mode(schedule_mode), timestamp, timestamp,
            ),
        )
        channel_id = int(cursor.fetchone()["id"]) if USE_POSTGRES else int(cursor.lastrowid)
        db.commit()
    return redirect_to(f"/channels/{channel_id}", "Canal criado com sucesso.")


@app.get("/channels/{channel_id}", response_class=HTMLResponse, name="channel_detail")
def channel_detail(request: Request, channel_id: int, status: str = "all", q: str = "", year: int | None = None):
    search = q.strip()
    with closing(get_db()) as db:
        channel = get_channel_or_404(db, channel_id)
        sql = "SELECT * FROM videos WHERE channel_id = ?"
        params: list[Any] = [channel_id]
        if status in STATUS_LABELS:
            sql += " AND status = ?"
            params.append(status)
        if search:
            sql += " AND (title LIKE ? OR description LIKE ?)"
            like = f"%{search}%"
            params.extend([like, like])
        sql += " ORDER BY CASE status WHEN 'production' THEN 1 ELSE 2 END, planned_date IS NULL, planned_date, updated_at DESC"
        videos = db.execute(sql, params).fetchall()
        stats = channel_stats(db, channel_id, channel["title_goal"])
        saved_titles = db.execute(
            "SELECT position, title, status FROM channel_titles WHERE channel_id = ? ORDER BY position",
            (channel_id,),
        ).fetchall()
        titles_by_position = {
            int(item["position"]): {
                "title": item["title"],
                "status": item["status"] if item["status"] in TITLE_STATUS_LABELS else "ready",
            }
            for item in saved_titles
        }
        highest_position = max(titles_by_position, default=0)
        title_slot_count = max(int(channel["title_goal"]), highest_position)
        title_slots = [
            {
                "position": position,
                "title": titles_by_position.get(position, {}).get("title", ""),
                "status": titles_by_position.get(position, {}).get("status", "ready"),
            }
            for position in range(1, title_slot_count + 1)
        ]
        daily_stats = daily_goal_stats(db, channel)
        projection = channel_projection(db, channel)
        upcoming = schedule_date_items(db, channel_id, projection["dates"])
        calendar_year = min(max(int(year or today_local().year), 2020), 2100)
        month_cards = month_calendar(db, channel_id, calendar_year)
    context = template_context(
        request,
        channel=channel,
        videos=videos,
        stats=stats,
        title_slots=title_slots,
        title_status_labels=TITLE_STATUS_LABELS,
        daily_stats=daily_stats,
        upcoming=upcoming,
        calendar_year=calendar_year,
        month_cards=month_cards,
        projection=projection,
        status_filter=status,
        search=search,
    )
    return templates.TemplateResponse(request, "channel.html", context)


@app.post("/channels/{channel_id}/daily-goals", name="save_daily_goals")
def save_daily_goals(
    channel_id: int, daily_script_goal: int = Form(1), daily_video_goal: int = Form(1),
):
    script_goal = min(max(int(daily_script_goal or 1), 1), 999)
    video_goal = min(max(int(daily_video_goal or 1), 1), 999)
    with closing(get_db()) as db:
        get_channel_or_404(db, channel_id)
        db.execute(
            "UPDATE channels SET daily_script_goal = ?, daily_video_goal = ?, updated_at = ? WHERE id = ?",
            (script_goal, video_goal, now_iso(), channel_id),
        )
        db.commit()
    return redirect_to(
        f"/channels/{channel_id}",
        f"Metas diárias atualizadas: {script_goal} roteiro(s) e {video_goal} vídeo(s) por dia.",
    )


@app.post("/channels/{channel_id}/edit", name="edit_channel")
def edit_channel(
    channel_id: int, name: str = Form(...), description: str = Form(""), title_goal: int = Form(...),
    interval_days: int = Form(...), frequency_mode: str = Form("interval"),
    schedule_mode: str = Form("standard"), start_date: str = Form(...), period_mode: str = Form("months"),
    period_value: str = Form("1"), planning_month: str = Form(""),
    calculation_days: str = Form(""), image: UploadFile | None = File(None),
    image_cloud_url: str = Form(""), image_cloud_name: str = Form(""),
    image_cloud_mime: str = Form(""), image_cloud_size: str = Form(""),
):
    old_image_to_remove = None
    with closing(get_db()) as db:
        channel = get_channel_or_404(db, channel_id)
        image_path = channel["image_path"]
        if image_cloud_url:
            try:
                _, new_image, file_type, _, _ = validate_cloud_upload(
                    image_cloud_url, image_cloud_name, image_cloud_mime, image_cloud_size,
                )
                if file_type != "image":
                    remove_upload(new_image)
                    raise ValueError("A capa do canal precisa ser uma imagem.")
                old_image_to_remove = image_path
                image_path = new_image
            except ValueError as exc:
                remove_upload(image_cloud_url)
                return redirect_to(f"/channels/{channel_id}", str(exc), "error")
        elif image and image.filename:
            try:
                _, new_image, file_type, _, _ = save_upload(image)
                if file_type != "image":
                    remove_upload(new_image)
                    raise ValueError("A capa do canal precisa ser uma imagem.")
                old_image_to_remove = image_path
                image_path = new_image
            except ValueError as exc:
                return redirect_to(f"/channels/{channel_id}", str(exc), "error")
        mode = normalize_frequency_mode(frequency_mode)
        frequency_value = normalize_frequency_value(interval_days, mode)
        parsed_start = parse_iso_date(start_date)
        normalized_period_mode = normalize_period_mode(period_mode)
        normalized_period_value = normalize_period_value(period_value, normalized_period_mode)
        selected_month = planning_month or str(channel["planning_month"] or "")
        period = calculate_period(parsed_start, normalized_period_mode, normalized_period_value, selected_month)
        db.execute(
            """UPDATE channels SET name = ?, description = ?, image_path = ?, title_goal = ?, interval_days = ?,
            frequency_mode = ?, start_date = ?, planning_month = ?, calculation_days = ?,
            period_mode = ?, period_value = ?, schedule_mode = ?, updated_at = ? WHERE id = ?""",
            (
                name.strip() or channel["name"], description.strip(), image_path, max(1, title_goal),
                frequency_value, mode, parsed_start.isoformat(), period["planning_month"],
                period["period_days"], period["period_mode"], period["period_value"],
                normalize_schedule_mode(schedule_mode), now_iso(), channel_id,
            ),
        )
        db.commit()
    if old_image_to_remove and old_image_to_remove != image_path:
        remove_upload(old_image_to_remove)
    return redirect_to(f"/channels/{channel_id}", "Configurações do canal atualizadas.")


@app.post("/channels/{channel_id}/titles", name="save_channel_titles")
async def save_channel_titles(request: Request, channel_id: int):
    form = await request.form()
    raw_titles = form.getlist("titles")[:200]
    raw_statuses = form.getlist("title_statuses")[:200]
    titles = [str(value).strip()[:500] for value in raw_titles]
    statuses = [
        str(value) if str(value) in TITLE_STATUS_LABELS else "ready"
        for value in raw_statuses
    ]
    timestamp = now_iso()
    with closing(get_db()) as db:
        channel = get_channel_or_404(db, channel_id)
        minimum_slots = max(1, int(channel["title_goal"] or 1))
        if len(titles) < minimum_slots:
            titles.extend([""] * (minimum_slots - len(titles)))
        if len(statuses) < len(titles):
            statuses.extend(["ready"] * (len(titles) - len(statuses)))
        for position, title in enumerate(titles, start=1):
            title_status = statuses[position - 1] if position - 1 < len(statuses) else "ready"
            if title:
                db.execute(
                    """INSERT INTO channel_titles (channel_id, position, title, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(channel_id, position) DO UPDATE SET
                    title = excluded.title, status = excluded.status, updated_at = excluded.updated_at""",
                    (channel_id, position, title, title_status, timestamp, timestamp),
                )
            else:
                db.execute(
                    "DELETE FROM channel_titles WHERE channel_id = ? AND position = ?",
                    (channel_id, position),
                )
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (timestamp, channel_id))
        db.commit()
        saved_count = db.execute(
            "SELECT COUNT(*) AS total FROM channel_titles WHERE channel_id = ? AND TRIM(title) <> ''",
            (channel_id,),
        ).fetchone()["total"]
    return redirect_to(
        f"/channels/{channel_id}",
        f"Banco de títulos salvo: {saved_count} título{'s' if saved_count != 1 else ''} preenchido{'s' if saved_count != 1 else ''}.",
    )


@app.post("/channels/{channel_id}/delete", name="delete_channel")
def delete_channel(channel_id: int):
    with closing(get_db()) as db:
        channel = get_channel_or_404(db, channel_id)
        files = db.execute(
            "SELECT attachments.stored_name FROM attachments JOIN videos ON videos.id = attachments.video_id WHERE videos.channel_id = ?",
            (channel_id,),
        ).fetchall()
        video_covers = db.execute(
            "SELECT cover_image_path FROM videos WHERE channel_id = ? AND cover_image_path IS NOT NULL",
            (channel_id,),
        ).fetchall()
        db.execute("DELETE FROM channels WHERE id = ?", (channel_id,))
        db.commit()
    remove_upload(channel["image_path"])
    for item in files:
        remove_upload(item["stored_name"])
    for item in video_covers:
        remove_upload(item["cover_image_path"])
    return redirect_to("/", "Canal excluído.")


@app.post("/channels/{channel_id}/videos", name="create_video")
def create_video(
    channel_id: int, title: str = Form(...), status: str = Form("production"),
    planned_date: str = Form(""), description: str = Form(""),
    cover_image: UploadFile | None = File(None),
    cover_cloud_url: str = Form(""), cover_cloud_name: str = Form(""),
    cover_cloud_mime: str = Form(""), cover_cloud_size: str = Form(""),
    return_to: str = Form(""),
):
    title = title.strip()
    if not title:
        return redirect_to(f"/channels/{channel_id}", "Digite um título para o card do vídeo.", "error")
    if status not in STATUS_LABELS:
        status = "production"
    cover_image_path = None
    if cover_cloud_url:
        try:
            _, cover_image_path, file_type, _, _ = validate_cloud_upload(
                cover_cloud_url, cover_cloud_name, cover_cloud_mime, cover_cloud_size,
            )
            if file_type != "image":
                remove_upload(cover_image_path)
                raise ValueError("A capa do vídeo precisa ser uma imagem.")
        except ValueError as exc:
            remove_upload(cover_cloud_url)
            return redirect_to(f"/channels/{channel_id}", str(exc), "error")
    elif cover_image and cover_image.filename:
        try:
            _, cover_image_path, file_type, _, _ = save_upload(cover_image)
            if file_type != "image":
                remove_upload(cover_image_path)
                raise ValueError("A capa do vídeo precisa ser uma imagem.")
        except ValueError as exc:
            return redirect_to(f"/channels/{channel_id}", str(exc), "error")
    timestamp = now_iso()
    insert_sql = """INSERT INTO videos (
        channel_id, title, status, planned_date, description, cover_image_path,
        script_completed_at, completed_at, published_at, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
    if USE_POSTGRES:
        insert_sql += " RETURNING id"
    with closing(get_db()) as db:
        get_channel_or_404(db, channel_id)
        completed_at = timestamp if status == "completed" else None
        cursor = db.execute(
            insert_sql,
            (
                channel_id, title, status, planned_date or None, description.strip(), cover_image_path,
                None, completed_at, None, timestamp, timestamp,
            ),
        )
        video_id = int(cursor.fetchone()["id"]) if USE_POSTGRES else int(cursor.lastrowid)
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (timestamp, channel_id))
        db.commit()
    destination = return_to if return_to.startswith("/channels/") else f"/videos/{video_id}"
    return redirect_to(destination, "Card de vídeo criado.")


@app.get("/videos/{video_id}", response_class=HTMLResponse, name="video_detail")
def video_detail(request: Request, video_id: int):
    with closing(get_db()) as db:
        video = get_video_or_404(db, video_id)
        attachments = db.execute("SELECT * FROM attachments WHERE video_id = ? ORDER BY created_at DESC", (video_id,)).fetchall()
        texts = db.execute("SELECT * FROM text_fields WHERE video_id = ? ORDER BY created_at DESC", (video_id,)).fetchall()
    return templates.TemplateResponse(request, "video.html", template_context(request, video=video, attachments=attachments, texts=texts))


@app.post("/videos/{video_id}/edit", name="edit_video")
def edit_video(
    video_id: int, title: str = Form(...), status: str = Form(...),
    planned_date: str = Form(""), description: str = Form(""),
    cover_image: UploadFile | None = File(None), remove_cover: str = Form(""),
    cover_cloud_url: str = Form(""), cover_cloud_name: str = Form(""),
    cover_cloud_mime: str = Form(""), cover_cloud_size: str = Form(""),
):
    with closing(get_db()) as db:
        video = get_video_or_404(db, video_id)
        if status not in STATUS_LABELS:
            status = video["status"] if video["status"] in STATUS_LABELS else "production"
        cover_image_path = video["cover_image_path"]
        old_cover_to_remove = None
        if remove_cover == "1" and cover_image_path:
            old_cover_to_remove = cover_image_path
            cover_image_path = None
        if cover_cloud_url:
            try:
                _, new_cover, file_type, _, _ = validate_cloud_upload(
                    cover_cloud_url, cover_cloud_name, cover_cloud_mime, cover_cloud_size,
                )
                if file_type != "image":
                    remove_upload(new_cover)
                    raise ValueError("A capa do vídeo precisa ser uma imagem.")
                old_cover_to_remove = video["cover_image_path"]
                cover_image_path = new_cover
            except ValueError as exc:
                remove_upload(cover_cloud_url)
                return redirect_to(f"/videos/{video_id}", str(exc), "error")
        elif cover_image and cover_image.filename:
            try:
                _, new_cover, file_type, _, _ = save_upload(cover_image)
                if file_type != "image":
                    remove_upload(new_cover)
                    raise ValueError("A capa do vídeo precisa ser uma imagem.")
                old_cover_to_remove = video["cover_image_path"]
                cover_image_path = new_cover
            except ValueError as exc:
                return redirect_to(f"/videos/{video_id}", str(exc), "error")
        timestamp = now_iso()
        completed_at = video["completed_at"]
        if status == "completed" and video["status"] != "completed":
            completed_at = timestamp
        elif status != "completed":
            completed_at = None
        db.execute(
            """UPDATE videos SET title = ?, description = ?, status = ?, planned_date = ?,
            cover_image_path = ?, completed_at = ?, updated_at = ? WHERE id = ?""",
            (
                title.strip() or video["title"], description.strip(), status, planned_date or None,
                cover_image_path, completed_at, timestamp, video_id,
            ),
        )
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (timestamp, video["channel_id"]))
        db.commit()
    if old_cover_to_remove and old_cover_to_remove != cover_image_path:
        remove_upload(old_cover_to_remove)
    return redirect_to(f"/videos/{video_id}", "Card atualizado.")


@app.post("/api/videos/{video_id}/status", name="api_video_status")
async def api_video_status(request: Request, video_id: int):
    payload = await request.json()
    status = payload.get("status")
    if status not in STATUS_LABELS:
        return JSONResponse({"ok": False, "message": "Status inválido"}, status_code=400)
    with closing(get_db()) as db:
        video = get_video_or_404(db, video_id)
        channel = get_channel_or_404(db, video["channel_id"])
        before_daily = daily_goal_stats(db, channel)
        before_stats = channel_stats(db, video["channel_id"], channel["title_goal"])
        timestamp = now_iso()
        completed_at = video["completed_at"]
        if status == "completed" and video["status"] != "completed":
            completed_at = timestamp
        elif status != "completed":
            completed_at = None
        db.execute(
            "UPDATE videos SET status = ?, completed_at = ?, updated_at = ? WHERE id = ?",
            (status, completed_at, timestamp, video_id),
        )
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (timestamp, video["channel_id"]))
        db.commit()
        after_daily = daily_goal_stats(db, channel)
        stats = channel_stats(db, video["channel_id"], channel["title_goal"])
        celebrate_kind = achieved_kind(
            before_daily, after_daily,
            bool(before_stats["completed"] >= before_stats["goal"]),
            bool(stats["completed"] >= stats["goal"]),
        )
    return {"ok": True, "label": STATUS_LABELS[status], "stats": stats, "celebration": celebration_payload(celebrate_kind)}


@app.post("/api/videos/{video_id}/script-ready", name="api_video_script_ready")
async def api_video_script_ready(request: Request, video_id: int):
    payload = await request.json()
    ready = bool(payload.get("ready"))
    with closing(get_db()) as db:
        video = get_video_or_404(db, video_id)
        channel = get_channel_or_404(db, video["channel_id"])
        before_daily = daily_goal_stats(db, channel)
        timestamp = now_iso()
        script_completed_at = timestamp if ready else None
        db.execute(
            "UPDATE videos SET script_completed_at = ?, updated_at = ? WHERE id = ?",
            (script_completed_at, timestamp, video_id),
        )
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (timestamp, video["channel_id"]))
        db.commit()
        daily_stats = daily_goal_stats(db, channel)
        celebrate_kind = achieved_kind(before_daily, daily_stats)
    return {"ok": True, "ready": ready, "daily_stats": daily_stats, "celebration": celebration_payload(celebrate_kind)}


@app.post("/api/videos/{video_id}/published", name="api_video_published")
async def api_video_published(request: Request, video_id: int):
    payload = await request.json()
    published = bool(payload.get("published"))
    with closing(get_db()) as db:
        video = get_video_or_404(db, video_id)
        timestamp = now_iso()
        published_at = timestamp if published else None
        db.execute(
            "UPDATE videos SET published_at = ?, updated_at = ? WHERE id = ?",
            (published_at, timestamp, video_id),
        )
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (timestamp, video["channel_id"]))
        db.commit()
    return {"ok": True, "published": published, "published_at": published_at}


@app.post("/videos/{video_id}/upload", name="upload_attachments")
def upload_attachments(
    video_id: int,
    files: list[UploadFile] | None = File(None),
    cloud_files_json: str = Form(""),
):
    inserted = 0
    errors: list[str] = []
    cloud_items: list[dict[str, Any]] = []
    if cloud_files_json.strip():
        try:
            decoded = json.loads(cloud_files_json)
            if isinstance(decoded, list):
                cloud_items = [item for item in decoded[:100] if isinstance(item, dict)]
        except json.JSONDecodeError:
            errors.append("A lista de arquivos enviados ficou inválida. Tente novamente.")
    with closing(get_db()) as db:
        video = get_video_or_404(db, video_id)
        for item in cloud_items:
            cloud_url = str(item.get("stored_name") or item.get("url") or "")
            try:
                original, stored, file_type, mime, size = validate_cloud_upload(
                    cloud_url,
                    str(item.get("original_name") or item.get("name") or "arquivo"),
                    str(item.get("mime_type") or item.get("type") or ""),
                    item.get("size_bytes") or item.get("size") or 0,
                )
                db.execute(
                    """INSERT INTO attachments (video_id, original_name, stored_name, file_type, mime_type, size_bytes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (video_id, original, stored, file_type, mime, size, now_iso()),
                )
                inserted += 1
            except ValueError as exc:
                remove_upload(cloud_url)
                errors.append(str(exc))
        for upload in files or []:
            if not upload.filename:
                continue
            try:
                original, stored, file_type, mime, size = save_upload(upload)
                db.execute(
                    """INSERT INTO attachments (video_id, original_name, stored_name, file_type, mime_type, size_bytes, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (video_id, original, stored, file_type, mime, size, now_iso()),
                )
                inserted += 1
            except ValueError as exc:
                errors.append(str(exc))
        timestamp = now_iso()
        if inserted:
            db.execute("UPDATE videos SET updated_at = ? WHERE id = ?", (timestamp, video_id))
            db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (timestamp, video["channel_id"]))
        db.commit()
    if errors and not inserted:
        return redirect_to(f"/videos/{video_id}", " | ".join(errors), "error")
    message = f"{inserted} arquivo(s) anexado(s)."
    if errors:
        message += " Alguns formatos foram ignorados."
    return redirect_to(f"/videos/{video_id}", message, "success" if inserted else "error")


@app.post("/videos/{video_id}/texts", name="add_text_field")
def add_text_field(video_id: int, label: str = Form(...), content: str = Form("")):
    with closing(get_db()) as db:
        video = get_video_or_404(db, video_id)
        timestamp = now_iso()
        db.execute(
            "INSERT INTO text_fields (video_id, label, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (video_id, label.strip() or "Texto", content.strip(), timestamp, timestamp),
        )
        db.execute("UPDATE videos SET updated_at = ? WHERE id = ?", (timestamp, video_id))
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (timestamp, video["channel_id"]))
        db.commit()
    return redirect_to(f"/videos/{video_id}", "Campo de texto adicionado.")


@app.post("/texts/{text_id}/edit", name="edit_text_field")
def edit_text_field(text_id: int, label: str = Form(...), content: str = Form("")):
    with closing(get_db()) as db:
        text = db.execute("SELECT * FROM text_fields WHERE id = ?", (text_id,)).fetchone()
        if text is None:
            raise HTTPException(status_code=404)
        db.execute("UPDATE text_fields SET label = ?, content = ?, updated_at = ? WHERE id = ?", (label.strip() or text["label"], content.strip(), now_iso(), text_id))
        db.commit()
    return redirect_to(f"/videos/{text['video_id']}", "Texto salvo.")


@app.post("/texts/{text_id}/delete", name="delete_text_field")
def delete_text_field(text_id: int):
    with closing(get_db()) as db:
        text = db.execute("SELECT * FROM text_fields WHERE id = ?", (text_id,)).fetchone()
        if text is None:
            raise HTTPException(status_code=404)
        db.execute("DELETE FROM text_fields WHERE id = ?", (text_id,))
        db.commit()
    return redirect_to(f"/videos/{text['video_id']}", "Campo de texto removido.")


@app.post("/attachments/{attachment_id}/delete", name="delete_attachment")
def delete_attachment(attachment_id: int):
    with closing(get_db()) as db:
        attachment = db.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
        if attachment is None:
            raise HTTPException(status_code=404)
        db.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))
        db.commit()
    remove_upload(attachment["stored_name"])
    return redirect_to(f"/videos/{attachment['video_id']}", "Anexo removido.")


@app.post("/videos/{video_id}/delete", name="delete_video")
def delete_video(video_id: int):
    with closing(get_db()) as db:
        video = get_video_or_404(db, video_id)
        files = db.execute("SELECT stored_name FROM attachments WHERE video_id = ?", (video_id,)).fetchall()
        db.execute("DELETE FROM videos WHERE id = ?", (video_id,))
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (now_iso(), video["channel_id"]))
        db.commit()
    for item in files:
        remove_upload(item["stored_name"])
    remove_upload(video["cover_image_path"])
    return redirect_to(f"/channels/{video['channel_id']}", "Card de vídeo excluído.")


@app.get("/channels/{channel_id}/months/{year_month}", response_class=HTMLResponse, name="monthly_plan")
def monthly_plan(request: Request, channel_id: int, year_month: str):
    normalized_month = valid_year_month(year_month)
    with closing(get_db()) as db:
        channel = get_channel_or_404(db, channel_id)
        plan = db.execute(
            "SELECT * FROM monthly_plans WHERE channel_id = ? AND year_month = ?",
            (channel_id, normalized_month),
        ).fetchone()
        rules = db.execute(
            "SELECT * FROM schedule_rules WHERE channel_id = ? AND year_month = ? ORDER BY start_date, id",
            (channel_id, normalized_month),
        ).fetchall()
        dates = custom_schedule_dates(db, channel_id, normalized_month)
        schedule_items = schedule_date_items(db, channel_id, dates)
        month_videos = db.execute(
            "SELECT * FROM videos WHERE channel_id = ? AND planned_date LIKE ? ORDER BY planned_date, updated_at DESC",
            (channel_id, f"{normalized_month}-%"),
        ).fetchall()
    year, month = parse_year_month(normalized_month)
    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    return templates.TemplateResponse(
        request,
        "monthly_plan.html",
        template_context(
            request,
            channel=channel,
            plan=plan,
            rules=rules,
            schedule_items=schedule_items,
            month_videos=month_videos,
            year_month=normalized_month,
            month_label=f"{MONTH_NAMES_PT[month]} de {year}",
            month_start=month_start.isoformat(),
            month_end=month_end.isoformat(),
            total_dates=len(dates),
        ),
    )


@app.post("/channels/{channel_id}/months/{year_month}/plan", name="save_monthly_plan")
def save_monthly_plan(channel_id: int, year_month: str, notes: str = Form("")):
    normalized_month = valid_year_month(year_month)
    timestamp = now_iso()
    with closing(get_db()) as db:
        get_channel_or_404(db, channel_id)
        db.execute(
            """INSERT INTO monthly_plans (channel_id, year_month, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(channel_id, year_month) DO UPDATE SET notes = excluded.notes, updated_at = excluded.updated_at""",
            (channel_id, normalized_month, notes.strip(), timestamp, timestamp),
        )
        db.execute(
            "UPDATE channels SET schedule_mode = 'custom', updated_at = ? WHERE id = ?",
            (timestamp, channel_id),
        )
        db.commit()
    return redirect_to(f"/channels/{channel_id}/months/{normalized_month}", "Planejamento mensal salvo.")


@app.post("/channels/{channel_id}/months/{year_month}/rules", name="add_schedule_rule")
def add_schedule_rule(
    channel_id: int, year_month: str, start_date: str = Form(...), end_date: str = Form(...),
    frequency_mode: str = Form("interval"), interval_days: int = Form(1),
):
    normalized_month = valid_year_month(year_month)
    year, month = parse_year_month(normalized_month)
    lower = date(year, month, 1)
    upper = date(year, month, calendar.monthrange(year, month)[1])
    start = parse_iso_date(start_date, lower)
    end = parse_iso_date(end_date, upper)
    if start < lower or start > upper or end < lower or end > upper:
        return redirect_to(
            f"/channels/{channel_id}/months/{normalized_month}",
            "As datas da regra precisam ficar dentro do mês selecionado.", "error",
        )
    if end < start:
        return redirect_to(f"/channels/{channel_id}/months/{normalized_month}", "A data final não pode vir antes da inicial.", "error")
    mode = normalize_frequency_mode(frequency_mode)
    value = normalize_frequency_value(interval_days, mode)
    timestamp = now_iso()
    with closing(get_db()) as db:
        get_channel_or_404(db, channel_id)
        db.execute(
            """INSERT INTO schedule_rules (
                channel_id, year_month, start_date, end_date, frequency_mode, interval_days, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (channel_id, normalized_month, start.isoformat(), end.isoformat(), mode, value, timestamp, timestamp),
        )
        db.execute(
            """INSERT INTO monthly_plans (channel_id, year_month, notes, created_at, updated_at)
            VALUES (?, ?, '', ?, ?)
            ON CONFLICT(channel_id, year_month) DO UPDATE SET updated_at = excluded.updated_at""",
            (channel_id, normalized_month, timestamp, timestamp),
        )
        db.execute("UPDATE channels SET schedule_mode = 'custom', updated_at = ? WHERE id = ?", (timestamp, channel_id))
        db.commit()
    return redirect_to(
        f"/channels/{channel_id}/months/{normalized_month}",
        "Regra adicionada. As datas e a quantidade de vídeos foram recalculadas.",
    )


@app.post("/schedule-rules/{rule_id}/delete", name="delete_schedule_rule")
def delete_schedule_rule(rule_id: int):
    with closing(get_db()) as db:
        rule = db.execute("SELECT * FROM schedule_rules WHERE id = ?", (rule_id,)).fetchone()
        if rule is None:
            raise HTTPException(status_code=404)
        db.execute("DELETE FROM schedule_rules WHERE id = ?", (rule_id,))
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (now_iso(), rule["channel_id"]))
        db.commit()
    return redirect_to(f"/channels/{rule['channel_id']}/months/{rule['year_month']}", "Regra removida.")


@app.get("/production-flow", response_class=HTMLResponse, name="production_flow")
def production_flow(request: Request, channel_id: int | None = None, month: str = ""):
    selected_month = valid_year_month(month)
    with closing(get_db()) as db:
        channels = db.execute("SELECT * FROM channels ORDER BY name").fetchall()
        selected_channel = None
        if channels:
            selected_id = int(channel_id or channels[0]["id"])
            selected_channel = next((item for item in channels if int(item["id"]) == selected_id), channels[0])
            selected_id = int(selected_channel["id"])
            logs = db.execute(
                "SELECT * FROM production_logs WHERE channel_id = ? AND history_month = ? ORDER BY work_date DESC, created_at DESC",
                (selected_id, selected_month),
            ).fetchall()
            month_rows = db.execute(
                "SELECT DISTINCT history_month FROM production_logs WHERE channel_id = ? ORDER BY history_month DESC",
                (selected_id,),
            ).fetchall()
            available_months = [row["history_month"] for row in month_rows]
            if selected_month not in available_months:
                available_months.insert(0, selected_month)
            default_work_date = today_local().isoformat() if today_local().strftime("%Y-%m") == selected_month else f"{selected_month}-01"
            grouped: list[dict[str, Any]] = []
            for work_date in sorted({row["work_date"] for row in logs}, reverse=True):
                entries = [row for row in logs if row["work_date"] == work_date]
                stats = daily_goal_stats(db, selected_channel, parse_iso_date(work_date))
                grouped.append({"date": work_date, "date_br": date_br(work_date), "entries": entries, "stats": stats})
        else:
            logs, available_months, grouped = [], [selected_month], []
            default_work_date = today_local().isoformat()
    return templates.TemplateResponse(
        request,
        "production_flow.html",
        template_context(
            request,
            channels=channels,
            selected_channel=selected_channel,
            selected_month=selected_month,
            available_months=available_months,
            grouped_logs=grouped,
            production_status_labels=PRODUCTION_LOG_STATUS,
            default_work_date=default_work_date,
        ),
    )


@app.post("/production-flow", name="add_production_log")
def add_production_log(
    channel_id: int = Form(...), history_month: str = Form(...), video_title: str = Form(...),
    work_date: str = Form(...), operator_name: str = Form(...), status: str = Form(...),
):
    normalized_month = valid_year_month(history_month)
    selected_date = parse_iso_date(work_date)
    if selected_date.strftime("%Y-%m") != normalized_month:
        return redirect_to(
            f"/production-flow?channel_id={channel_id}&month={normalized_month}",
            "A data precisa pertencer ao mês escolhido para o histórico.", "error",
        )
    if status not in PRODUCTION_LOG_STATUS:
        return redirect_to(f"/production-flow?channel_id={channel_id}&month={normalized_month}", "Status inválido.", "error")
    if not video_title.strip() or not operator_name.strip():
        return redirect_to(f"/production-flow?channel_id={channel_id}&month={normalized_month}", "Preencha o título e o nome do operador.", "error")
    timestamp = now_iso()
    with closing(get_db()) as db:
        channel = get_channel_or_404(db, channel_id)
        before = daily_goal_stats(db, channel, selected_date)
        db.execute(
            """INSERT INTO production_logs (
                channel_id, history_month, video_title, work_date, operator_name, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (channel_id, normalized_month, video_title.strip(), selected_date.isoformat(), operator_name.strip(), status, timestamp, timestamp),
        )
        db.commit()
        after = daily_goal_stats(db, channel, selected_date)
        celebrate_kind = achieved_kind(before, after)
    target = f"/production-flow?channel_id={channel_id}&month={normalized_month}"
    if celebrate_kind:
        target += f"&celebrate={celebrate_kind}"
    return redirect_to(target, "Atividade adicionada ao Fluxo de Produção.")


@app.post("/production-flow/{log_id}/delete", name="delete_production_log")
def delete_production_log(log_id: int):
    with closing(get_db()) as db:
        entry = db.execute("SELECT * FROM production_logs WHERE id = ?", (log_id,)).fetchone()
        if entry is None:
            raise HTTPException(status_code=404)
        db.execute("DELETE FROM production_logs WHERE id = ?", (log_id,))
        db.commit()
    return redirect_to(
        f"/production-flow?channel_id={entry['channel_id']}&month={entry['history_month']}",
        "Atividade removida do histórico.",
    )


@app.get("/uploads/{filename:path}", name="uploaded_file")
def uploaded_file(filename: str):
    if filename.startswith(("https://", "http://")):
        if not is_vercel_blob_url(filename):
            raise HTTPException(status_code=404)
        return RedirectResponse(filename, status_code=307)
    path = UPLOAD_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path)


@app.exception_handler(404)
async def not_found(request: Request, _exc):
    return templates.TemplateResponse(request, "404.html", template_context(request), status_code=404)


try:
    init_db()
except Exception:
    if IS_VERCEL:
        CONFIG_ERRORS.append(
            "Não foi possível conectar ou preparar o banco Postgres. Confira DATABASE_URL e faça um novo deploy."
        )
    else:
        raise

if __name__ == "__main__":
    port = int(os.environ.get("PLANNERX_PORT", "5050"))
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False)
