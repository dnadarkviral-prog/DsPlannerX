from __future__ import annotations

import calendar
import mimetypes
import os
import shutil
import sqlite3
import uuid
from contextlib import closing
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "plannerx.db"
UPLOAD_DIR = BASE_DIR / "static" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {
    "mp4", "mov", "mkv", "avi", "webm", "m4v",
    "mp3", "wav", "m4a", "aac", "ogg", "flac",
    "png", "jpg", "jpeg", "webp", "gif", "svg",
    "txt", "md", "srt", "pdf",
}

STATUS_LABELS = {
    "todo": "Pra fazer",
    "production": "Em produção",
    "completed": "Concluído",
}

FREQUENCY_MODES = {
    "interval": "Intervalo entre postagens",
    "days_off": "Dias completos sem postar",
}

app = FastAPI(title="DS - PLANNERX", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def get_db() -> sqlite3.Connection:
    db = sqlite3.connect(DATABASE_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def init_db() -> None:
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
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'todo' CHECK(status IN ('todo', 'production', 'completed')),
        planned_date TEXT,
        description TEXT NOT NULL DEFAULT '',
        cover_image_path TEXT,
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
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY(channel_id) REFERENCES channels(id) ON DELETE CASCADE,
        UNIQUE(channel_id, position)
    );

    CREATE TABLE IF NOT EXISTS posting_periods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id INTEGER NOT NULL,
        name TEXT NOT NULL DEFAULT '',
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        interval_days INTEGER NOT NULL DEFAULT 1,
        frequency_mode TEXT NOT NULL DEFAULT 'interval',
        videos_per_day INTEGER NOT NULL DEFAULT 1,
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

        channel_columns = {row["name"] for row in db.execute("PRAGMA table_info(channels)").fetchall()}
        if "frequency_mode" not in channel_columns:
            db.execute("ALTER TABLE channels ADD COLUMN frequency_mode TEXT NOT NULL DEFAULT 'interval'")
        db.execute(
            "UPDATE channels SET frequency_mode = 'interval' "
            "WHERE frequency_mode IS NULL OR frequency_mode NOT IN ('interval', 'days_off')"
        )

        period_columns = {row["name"] for row in db.execute("PRAGMA table_info(posting_periods)").fetchall()}
        if "videos_per_day" not in period_columns:
            db.execute("ALTER TABLE posting_periods ADD COLUMN videos_per_day INTEGER NOT NULL DEFAULT 1")
        db.execute("UPDATE posting_periods SET videos_per_day = 1 WHERE videos_per_day IS NULL OR videos_per_day < 1")
        db.execute(
            "UPDATE posting_periods SET frequency_mode = 'interval' "
            "WHERE frequency_mode IS NULL OR frequency_mode NOT IN ('interval', 'days_off')"
        )
        db.commit()


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def parse_iso_date(value: str | None, fallback: date | None = None) -> date:
    if value:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            pass
    return fallback or date.today()


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


def remove_upload(filename: str | None) -> None:
    if not filename:
        return
    path = UPLOAD_DIR / filename
    if path.exists() and path.is_file():
        path.unlink(missing_ok=True)


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


def first_schedule_date(start: date, step_days: int) -> date:
    """Mantém a cadência escolhida e encontra a primeira data ainda válida."""
    step_days = max(1, step_days)
    current = start
    today = date.today()
    if current < today:
        elapsed = (today - current).days
        jumps = (elapsed + step_days - 1) // step_days
        current += timedelta(days=jumps * step_days)
    return current


def end_of_next_month(reference: date) -> date:
    """Retorna o último dia do mês seguinte ao da data de referência."""
    if reference.month == 12:
        year, month = reference.year + 1, 1
    else:
        year, month = reference.year, reference.month + 1
    return date(year, month, calendar.monthrange(year, month)[1])


def schedule_dates_until(start: date, step_days: int, period_end: date) -> list[date]:
    """Gera todas as datas da agenda, sem limite visual artificial."""
    step_days = max(1, step_days)
    dates: list[date] = []
    current = start
    while current <= period_end:
        dates.append(current)
        current += timedelta(days=step_days)
    return dates


def month_projection(start: date, interval_days: int, frequency_mode: str = "interval") -> dict[str, Any]:
    """Calcula a agenda do início selecionado até o fim do mês seguinte.

    ``interval`` mede a distância entre as datas: dia 27, a cada 2 dias,
    resulta em 27, 29, 31. ``days_off`` mede quantos dias completos ficam sem
    postagem: dia 27, com 2 dias sem postar, resulta em 27, 30, 02.

    Exemplo pedido: de 27/07/2026 até 31/08/2026, com 2 dias completos sem
    postar, são 12 publicações: 27/07, 30/07, 02/08 ... 29/08.
    """
    mode = normalize_frequency_mode(frequency_mode)
    value = normalize_frequency_value(interval_days, mode)
    step_days = effective_interval_days(value, mode)
    first_date = first_schedule_date(start, step_days)
    period_end = end_of_next_month(first_date)
    dates = schedule_dates_until(first_date, step_days, period_end)
    return {
        "count": len(dates),
        "dates": dates,
        "period_days": (period_end - first_date).days + 1,
        "period_start": first_date,
        "period_end": period_end,
        "frequency_mode": mode,
        "frequency_value": value,
        "step_days": step_days,
        "frequency_text": frequency_text(value, mode),
        "frequency_text_compact": frequency_text(value, mode, compact=True),
    }


PT_MONTHS = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def end_of_month(reference: date) -> date:
    return date(reference.year, reference.month, calendar.monthrange(reference.year, reference.month)[1])


def ensure_posting_periods(db: sqlite3.Connection, channel: sqlite3.Row) -> list[sqlite3.Row]:
    periods = db.execute(
        "SELECT * FROM posting_periods WHERE channel_id = ? ORDER BY start_date, id",
        (channel["id"],),
    ).fetchall()
    if periods:
        return periods

    start = parse_iso_date(channel["start_date"])
    timestamp = now_iso()
    label = f"Planejamento de {PT_MONTHS[start.month].lower()}"
    db.execute(
        """INSERT INTO posting_periods
        (channel_id, name, start_date, end_date, interval_days, frequency_mode, videos_per_day, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
        (
            channel["id"], label, start.isoformat(), end_of_next_month(start).isoformat(),
            normalize_frequency_value(channel["interval_days"], normalize_frequency_mode(channel["frequency_mode"])),
            normalize_frequency_mode(channel["frequency_mode"]), timestamp, timestamp,
        ),
    )
    db.commit()
    return db.execute(
        "SELECT * FROM posting_periods WHERE channel_id = ? ORDER BY start_date, id",
        (channel["id"],),
    ).fetchall()


def period_dates(period: sqlite3.Row | dict[str, Any]) -> list[date]:
    start = parse_iso_date(period["start_date"])
    end = parse_iso_date(period["end_date"], start)
    if end < start:
        start, end = end, start
    mode = normalize_frequency_mode(period["frequency_mode"])
    value = normalize_frequency_value(period["interval_days"], mode)
    return schedule_dates_until(start, effective_interval_days(value, mode), end)


def combined_period_projection(
    periods: list[sqlite3.Row],
    video_counts: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    """Une os períodos sem transformar sobreposição em vídeos extras.

    Uma data que aparece em dois ou mais períodos continua sendo uma única data.
    A quantidade de vídeos daquele dia é definida explicitamente pelo campo
    ``videos_per_day``. Se períodos sobrepostos tiverem valores diferentes,
    prevalece o maior valor, nunca a soma automática.
    """
    merged: dict[date, dict[str, int]] = {}
    for period in periods:
        videos_per_day = max(1, int(period["videos_per_day"] or 1))
        for scheduled_date in period_dates(period):
            item = merged.setdefault(scheduled_date, {"videos_per_day": 1, "source_count": 0})
            item["videos_per_day"] = max(item["videos_per_day"], videos_per_day)
            item["source_count"] += 1

    dates = sorted(merged)
    counts = video_counts or {}
    schedule: list[dict[str, Any]] = []
    today = date.today()
    first_future_seen = False
    total_videos = 0

    for scheduled_date in dates:
        key = scheduled_date.isoformat()
        configured = merged[scheduled_date]["videos_per_day"]
        assigned = int(counts.get(key, {}).get("assigned", 0))
        completed = int(counts.get(key, {}).get("completed", 0))
        planned = max(configured, assigned)
        total_videos += planned

        if scheduled_date < today and completed >= planned:
            status_text, status_class = "Publicado", "published"
        elif scheduled_date == today:
            status_text, status_class = "Postagem de hoje", "today"
        elif scheduled_date < today:
            status_text, status_class = "Postagem pendente", "late"
        elif not first_future_seen:
            status_text, status_class = "Próxima postagem", "next"
            first_future_seen = True
        else:
            status_text, status_class = "Postagem prevista", "future"

        schedule.append({
            "date": scheduled_date,
            "videos_per_day": planned,
            "configured_videos_per_day": configured,
            "source_count": merged[scheduled_date]["source_count"],
            "assigned": assigned,
            "completed": completed,
            "status_text": status_text,
            "status_class": status_class,
        })

    if dates:
        period_start, period_end = dates[0], dates[-1]
    else:
        period_start = period_end = date.today()

    if period_start.month == period_end.month and period_start.year == period_end.year:
        period_label = f"{PT_MONTHS[period_start.month]} de {period_start.year}"
    else:
        period_label = f"{date_br(period_start)} a {date_br(period_end)}"

    period_count = len(periods)
    return {
        "count": total_videos,
        "date_count": len(dates),
        "dates": dates,
        "schedule": schedule,
        "period_start": period_start,
        "period_end": period_end,
        "period_days": (period_end - period_start).days + 1 if dates else 0,
        "period_count": period_count,
        "period_label": period_label,
        "frequency_mode": "multi" if period_count > 1 else (normalize_frequency_mode(periods[0]["frequency_mode"]) if periods else "interval"),
        "frequency_text": f"{period_count} período{'s' if period_count != 1 else ''} configurado{'s' if period_count != 1 else ''}",
        "frequency_text_compact": f"{period_count} período{'s' if period_count != 1 else ''}",
    }


def channel_video_counts_by_date(db: sqlite3.Connection, channel_id: int) -> dict[str, dict[str, int]]:
    rows = db.execute(
        """SELECT planned_date, COUNT(*) AS assigned,
        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) AS completed
        FROM videos
        WHERE channel_id = ? AND planned_date IS NOT NULL AND TRIM(planned_date) <> ''
        GROUP BY planned_date""",
        (channel_id,),
    ).fetchall()
    return {
        str(row["planned_date"]): {"assigned": int(row["assigned"] or 0), "completed": int(row["completed"] or 0)}
        for row in rows
    }


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
    remaining_titles = max(goal - title_count, 0)
    progress = min(counts["completed"] / goal * 100, 100)
    title_progress = min(title_count / goal * 100, 100)
    return {
        **counts,
        "total": total,
        "goal": goal,
        "title_count": title_count,
        "remaining_titles": remaining_titles,
        "progress": round(progress, 1),
        "title_progress": round(title_progress, 1),
    }


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
        "today": date.today().isoformat(),
        "messages": messages,
        "active_endpoint": active_endpoint,
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


@app.get("/", response_class=HTMLResponse, name="dashboard")
def dashboard(request: Request):
    with closing(get_db()) as db:
        channels = db.execute("SELECT * FROM channels ORDER BY updated_at DESC").fetchall()
        cards = []
        aggregate = {"channels": len(channels), "todo": 0, "production": 0, "completed": 0, "total": 0}
        for channel in channels:
            stats = channel_stats(db, channel["id"], channel["title_goal"])
            periods = ensure_posting_periods(db, channel)
            projection = combined_period_projection(periods, channel_video_counts_by_date(db, channel["id"]))
            cards.append({"channel": channel, "stats": stats, "projection": projection})
            for key in ("todo", "production", "completed", "total"):
                aggregate[key] += int(stats[key])
    return templates.TemplateResponse(request, "dashboard.html", template_context(request, cards=cards, aggregate=aggregate))


@app.post("/channels", name="create_channel")
def create_channel(
    name: str = Form(...), description: str = Form(""), title_goal: int = Form(12),
    interval_days: int = Form(2), frequency_mode: str = Form("interval"),
    start_date: str = Form(...), image: UploadFile | None = File(None),
):
    name = name.strip()
    if not name:
        return redirect_to("/", "Informe o nome do canal.", "error")
    image_path = None
    if image and image.filename:
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
    with closing(get_db()) as db:
        cursor = db.execute(
            """INSERT INTO channels (name, description, image_path, title_goal, interval_days, frequency_mode, start_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, description.strip(), image_path, max(1, title_goal), frequency_value, mode, parse_iso_date(start_date).isoformat(), timestamp, timestamp),
        )
        channel_id = cursor.lastrowid
        start = parse_iso_date(start_date)
        db.execute(
            """INSERT INTO posting_periods
            (channel_id, name, start_date, end_date, interval_days, frequency_mode, videos_per_day, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)""",
            (
                channel_id, f"Planejamento de {PT_MONTHS[start.month].lower()}", start.isoformat(),
                end_of_month(start).isoformat(), frequency_value, mode, timestamp, timestamp,
            ),
        )
        db.commit()
    return redirect_to(f"/channels/{channel_id}", "Canal criado com sucesso.")


@app.get("/channels/{channel_id}", response_class=HTMLResponse, name="channel_detail")
def channel_detail(request: Request, channel_id: int, status: str = "all", q: str = ""):
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
        sql += " ORDER BY CASE status WHEN 'production' THEN 1 WHEN 'todo' THEN 2 ELSE 3 END, planned_date IS NULL, planned_date, updated_at DESC"
        videos = db.execute(sql, params).fetchall()
        stats = channel_stats(db, channel_id, channel["title_goal"])
        saved_titles = db.execute(
            "SELECT position, title FROM channel_titles WHERE channel_id = ? ORDER BY position",
            (channel_id,),
        ).fetchall()
        titles_by_position = {int(item["position"]): item["title"] for item in saved_titles}
        highest_position = max(titles_by_position, default=0)
        title_slot_count = max(int(channel["title_goal"]), highest_position)
        title_slots = [
            {"position": position, "title": titles_by_position.get(position, "")}
            for position in range(1, title_slot_count + 1)
        ]
        periods = ensure_posting_periods(db, channel)
        projection = combined_period_projection(periods, channel_video_counts_by_date(db, channel_id))
        upcoming = projection["schedule"]
    context = template_context(
        request,
        channel=channel,
        videos=videos,
        stats=stats,
        title_slots=title_slots,
        periods=periods,
        upcoming=upcoming,
        projection=projection,
        status_filter=status,
        search=search,
    )
    return templates.TemplateResponse(request, "channel.html", context)


@app.post("/channels/{channel_id}/edit", name="edit_channel")
def edit_channel(
    channel_id: int, name: str = Form(...), description: str = Form(""), title_goal: int = Form(...),
    interval_days: int = Form(...), frequency_mode: str = Form("interval"),
    start_date: str = Form(...), image: UploadFile | None = File(None),
):
    with closing(get_db()) as db:
        channel = get_channel_or_404(db, channel_id)
        image_path = channel["image_path"]
        if image and image.filename:
            try:
                _, new_image, file_type, _, _ = save_upload(image)
                if file_type != "image":
                    remove_upload(new_image)
                    raise ValueError("A capa do canal precisa ser uma imagem.")
                remove_upload(image_path)
                image_path = new_image
            except ValueError as exc:
                return redirect_to(f"/channels/{channel_id}", str(exc), "error")
        mode = normalize_frequency_mode(frequency_mode)
        frequency_value = normalize_frequency_value(interval_days, mode)
        db.execute(
            """UPDATE channels SET name = ?, description = ?, image_path = ?, title_goal = ?, interval_days = ?,
            frequency_mode = ?, start_date = ?, updated_at = ? WHERE id = ?""",
            (name.strip() or channel["name"], description.strip(), image_path, max(1, title_goal), frequency_value, mode, parse_iso_date(start_date).isoformat(), now_iso(), channel_id),
        )
        db.commit()
    return redirect_to(f"/channels/{channel_id}", "Configurações do canal atualizadas.")


def validate_period_values(
    start_date: str, end_date: str, interval_days: int, frequency_mode: str, videos_per_day: int
) -> tuple[date, date, str, int, int]:
    start = parse_iso_date(start_date)
    end = parse_iso_date(end_date, start)
    if end < start:
        raise ValueError("A data final do período não pode ser anterior à data inicial.")
    mode = normalize_frequency_mode(frequency_mode)
    value = normalize_frequency_value(interval_days, mode)
    daily = max(1, min(int(videos_per_day or 1), 50))
    return start, end, mode, value, daily


@app.post("/channels/{channel_id}/periods", name="create_posting_period")
def create_posting_period(
    channel_id: int, name: str = Form(""), start_date: str = Form(...), end_date: str = Form(...),
    interval_days: int = Form(1), frequency_mode: str = Form("interval"),
    videos_per_day: int = Form(1),
):
    try:
        start, end, mode, value, daily = validate_period_values(
            start_date, end_date, interval_days, frequency_mode, videos_per_day
        )
    except ValueError as exc:
        return redirect_to(f"/channels/{channel_id}", str(exc), "error")
    timestamp = now_iso()
    period_name = name.strip() or f"Planejamento de {PT_MONTHS[start.month].lower()}"
    with closing(get_db()) as db:
        get_channel_or_404(db, channel_id)
        db.execute(
            """INSERT INTO posting_periods
            (channel_id, name, start_date, end_date, interval_days, frequency_mode, videos_per_day, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (channel_id, period_name, start.isoformat(), end.isoformat(), value, mode, daily, timestamp, timestamp),
        )
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (timestamp, channel_id))
        db.commit()
    return redirect_to(f"/channels/{channel_id}", "Período adicionado e calendário recalculado.")


@app.post("/periods/{period_id}/edit", name="edit_posting_period")
def edit_posting_period(
    period_id: int, name: str = Form(""), start_date: str = Form(...), end_date: str = Form(...),
    interval_days: int = Form(1), frequency_mode: str = Form("interval"),
    videos_per_day: int = Form(1),
):
    with closing(get_db()) as db:
        period = db.execute("SELECT * FROM posting_periods WHERE id = ?", (period_id,)).fetchone()
        if period is None:
            raise HTTPException(status_code=404, detail="Período não encontrado")
        channel_id = int(period["channel_id"])
        try:
            start, end, mode, value, daily = validate_period_values(
                start_date, end_date, interval_days, frequency_mode, videos_per_day
            )
        except ValueError as exc:
            return redirect_to(f"/channels/{channel_id}", str(exc), "error")
        timestamp = now_iso()
        period_name = name.strip() or f"Planejamento de {PT_MONTHS[start.month].lower()}"
        db.execute(
            """UPDATE posting_periods SET name = ?, start_date = ?, end_date = ?, interval_days = ?,
            frequency_mode = ?, videos_per_day = ?, updated_at = ? WHERE id = ?""",
            (period_name, start.isoformat(), end.isoformat(), value, mode, daily, timestamp, period_id),
        )
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (timestamp, channel_id))
        db.commit()
    return redirect_to(f"/channels/{channel_id}", "Período atualizado. Quantidades e datas foram recalculadas.")


@app.post("/periods/{period_id}/delete", name="delete_posting_period")
def delete_posting_period(period_id: int):
    with closing(get_db()) as db:
        period = db.execute("SELECT * FROM posting_periods WHERE id = ?", (period_id,)).fetchone()
        if period is None:
            raise HTTPException(status_code=404, detail="Período não encontrado")
        channel_id = int(period["channel_id"])
        total = int(db.execute(
            "SELECT COUNT(*) AS total FROM posting_periods WHERE channel_id = ?", (channel_id,)
        ).fetchone()["total"])
        if total <= 1:
            return redirect_to(f"/channels/{channel_id}", "Mantenha ao menos um período de postagem.", "error")
        db.execute("DELETE FROM posting_periods WHERE id = ?", (period_id,))
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (now_iso(), channel_id))
        db.commit()
    return redirect_to(f"/channels/{channel_id}", "Período removido sem duplicar datas restantes.")


@app.post("/channels/{channel_id}/titles", name="save_channel_titles")
async def save_channel_titles(request: Request, channel_id: int):
    form = await request.form()
    raw_titles = form.getlist("titles")[:200]
    titles = [str(value).strip()[:500] for value in raw_titles]
    timestamp = now_iso()
    with closing(get_db()) as db:
        channel = get_channel_or_404(db, channel_id)
        minimum_slots = max(1, int(channel["title_goal"] or 1))
        if len(titles) < minimum_slots:
            titles.extend([""] * (minimum_slots - len(titles)))
        for position, title in enumerate(titles, start=1):
            if title:
                db.execute(
                    """INSERT INTO channel_titles (channel_id, position, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(channel_id, position) DO UPDATE SET
                    title = excluded.title, updated_at = excluded.updated_at""",
                    (channel_id, position, title, timestamp, timestamp),
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
    channel_id: int, title: str = Form(...), status: str = Form("todo"),
    planned_date: str = Form(""), description: str = Form(""),
    cover_image: UploadFile | None = File(None),
):
    title = title.strip()
    if not title:
        return redirect_to(f"/channels/{channel_id}", "Digite um título para o card do vídeo.", "error")
    if status not in STATUS_LABELS:
        status = "todo"
    cover_image_path = None
    if cover_image and cover_image.filename:
        try:
            _, cover_image_path, file_type, _, _ = save_upload(cover_image)
            if file_type != "image":
                remove_upload(cover_image_path)
                raise ValueError("A capa do vídeo precisa ser uma imagem.")
        except ValueError as exc:
            return redirect_to(f"/channels/{channel_id}", str(exc), "error")
    timestamp = now_iso()
    with closing(get_db()) as db:
        get_channel_or_404(db, channel_id)
        cursor = db.execute(
            """INSERT INTO videos (channel_id, title, status, planned_date, description, cover_image_path, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (channel_id, title, status, planned_date or None, description.strip(), cover_image_path, timestamp, timestamp),
        )
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (timestamp, channel_id))
        db.commit()
        video_id = cursor.lastrowid
    return redirect_to(f"/videos/{video_id}", "Card de vídeo criado.")


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
):
    with closing(get_db()) as db:
        video = get_video_or_404(db, video_id)
        if status not in STATUS_LABELS:
            status = video["status"]
        cover_image_path = video["cover_image_path"]
        old_cover_to_remove = None
        if remove_cover == "1" and cover_image_path:
            old_cover_to_remove = cover_image_path
            cover_image_path = None
        if cover_image and cover_image.filename:
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
        db.execute(
            "UPDATE videos SET title = ?, description = ?, status = ?, planned_date = ?, cover_image_path = ?, updated_at = ? WHERE id = ?",
            (title.strip() or video["title"], description.strip(), status, planned_date or None, cover_image_path, timestamp, video_id),
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
        timestamp = now_iso()
        db.execute("UPDATE videos SET status = ?, updated_at = ? WHERE id = ?", (status, timestamp, video_id))
        db.execute("UPDATE channels SET updated_at = ? WHERE id = ?", (timestamp, video["channel_id"]))
        db.commit()
        channel = get_channel_or_404(db, video["channel_id"])
        stats = channel_stats(db, video["channel_id"], channel["title_goal"])
    return {"ok": True, "label": STATUS_LABELS[status], "stats": stats}


@app.post("/videos/{video_id}/upload", name="upload_attachments")
def upload_attachments(video_id: int, files: list[UploadFile] = File(...)):
    inserted = 0
    errors: list[str] = []
    with closing(get_db()) as db:
        video = get_video_or_404(db, video_id)
        for upload in files:
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


@app.get("/uploads/{filename:path}", name="uploaded_file")
def uploaded_file(filename: str):
    path = UPLOAD_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path)


@app.exception_handler(404)
async def not_found(request: Request, _exc):
    return templates.TemplateResponse(request, "404.html", template_context(request), status_code=404)


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PLANNERX_PORT", "5050"))
    uvicorn.run(app, host="127.0.0.1", port=port, reload=False)
