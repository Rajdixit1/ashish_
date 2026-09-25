from datetime import datetime, timezone
from hashlib import pbkdf2_hmac
from pathlib import Path
import os
import secrets
import sqlite3

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None

INTEGRITY_ERRORS = (sqlite3.IntegrityError, psycopg.IntegrityError) if psycopg else (sqlite3.IntegrityError,)
from fastapi import FastAPI, Form, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "hstaskgroup.db"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
USE_POSTGRES = bool(DATABASE_URL)
app = FastAPI(title="HS Task Group", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
SESSIONS: dict[str, tuple[int, str]] = {}

TASKS = [
    {"title": "Watch a YouTube video", "detail": "30 seconds", "reward": "Rs 25", "icon": "play"},
    {"title": "Leave a Google review", "detail": "Short template provided", "reward": "Rs 50", "icon": "star"},
    {"title": "Follow a social page", "detail": "Screenshot required", "reward": "Rs 35", "icon": "users"},
    {"title": "Install and open an app", "detail": "Free to join", "reward": "Rs 75", "icon": "download"},
]
ADMIN_NAME = "HS Task Group Admin"
ADMIN_MOBILE = "9999999999"

class PostgresRow(dict):
    def __getitem__(self, key: object) -> object:
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class PostgresCursor:
    def __init__(self, cursor: object) -> None:
        self.cursor = cursor

    def fetchone(self) -> PostgresRow | None:
        row = self.cursor.fetchone()
        return PostgresRow(row) if row else None

    def fetchall(self) -> list[PostgresRow]:
        return [PostgresRow(row) for row in self.cursor.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())


class PostgresConnection:
    def __init__(self, connection: object) -> None:
        self.connection = connection

    def execute(self, query: str, parameters: tuple = ()) -> PostgresCursor:
        return PostgresCursor(self.connection.execute(query.replace("?", "%s"), parameters))

    def executemany(self, query: str, parameters: list[tuple]) -> None:
        with self.connection.cursor() as cursor:
            cursor.executemany(query.replace("?", "%s"), parameters)

    def __enter__(self) -> "PostgresConnection":
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        if exception_type:
            self.connection.rollback()
        else:
            self.connection.commit()
        self.connection.close()


def connect_db() -> sqlite3.Connection | PostgresConnection:
    if USE_POSTGRES:
        if psycopg is None:
            raise RuntimeError("psycopg is required when DATABASE_URL is set.")
        return PostgresConnection(psycopg.connect(DATABASE_URL, row_factory=dict_row))
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection

def password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"{salt.hex()}${digest.hex()}"

def password_matches(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split("$", 1)
        candidate = pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 120_000).hex()
        return secrets.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError):
        return False

def init_database() -> None:
    with connect_db() as connection:
        if USE_POSTGRES:
            connection.execute("""CREATE TABLE IF NOT EXISTS clients (
                id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, mobile TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'client',
                status TEXT NOT NULL DEFAULT 'Pending', tasks_completed INTEGER NOT NULL DEFAULT 0,
                total_earned INTEGER NOT NULL DEFAULT 0, balance INTEGER NOT NULL DEFAULT 0,
                bank_details TEXT NOT NULL DEFAULT '', joined_at TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id BIGSERIAL PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                reward INTEGER NOT NULL, sort_order INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active',
                created_at TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS client_tasks (
                client_id BIGINT NOT NULL, task_id BIGINT NOT NULL, status TEXT NOT NULL DEFAULT 'completed',
                completed_at TEXT NOT NULL, PRIMARY KEY (client_id, task_id),
                FOREIGN KEY (client_id) REFERENCES clients(id), FOREIGN KEY (task_id) REFERENCES tasks(id))""")
            connection.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
                id BIGSERIAL PRIMARY KEY, client_id BIGINT NOT NULL, amount INTEGER NOT NULL,
                bank_details TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending', created_at TEXT NOT NULL,
                completed_at TEXT, FOREIGN KEY (client_id) REFERENCES clients(id))""")
        else:
            connection.execute("""CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, mobile TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'client', status TEXT NOT NULL DEFAULT 'Pending',
                tasks_completed INTEGER NOT NULL DEFAULT 0, total_earned INTEGER NOT NULL DEFAULT 0,
                joined_at TEXT NOT NULL)""")
            columns = {row[1] for row in connection.execute("PRAGMA table_info(clients)").fetchall()}
            if "balance" not in columns:
                connection.execute("ALTER TABLE clients ADD COLUMN balance INTEGER NOT NULL DEFAULT 0")
            if "bank_details" not in columns:
                connection.execute("ALTER TABLE clients ADD COLUMN bank_details TEXT NOT NULL DEFAULT ''")
            connection.execute("""CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL,
                reward INTEGER NOT NULL, sort_order INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS client_tasks (
                client_id INTEGER NOT NULL, task_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'completed',
                completed_at TEXT NOT NULL, PRIMARY KEY (client_id, task_id), FOREIGN KEY (client_id) REFERENCES clients(id),
                FOREIGN KEY (task_id) REFERENCES tasks(id))""")
            connection.execute("""CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT, client_id INTEGER NOT NULL, amount INTEGER NOT NULL,
                bank_details TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending', created_at TEXT NOT NULL,
                completed_at TEXT, FOREIGN KEY (client_id) REFERENCES clients(id))""")
        if connection.execute("SELECT COUNT(*) AS task_count FROM tasks").fetchone()["task_count"] == 0:
            seed_tasks = [("Task 1", "Watch a short video and follow the instructions.", 10), ("Task 2", "Leave a short review using the provided template.", 15), ("Task 3", "Follow a social page and submit proof.", 12), ("Task 4", "Install and open a free app.", 20), ("Task 5", "Share the task page with a friend.", 18)]
            connection.executemany(
                "INSERT INTO tasks (title, description, reward, sort_order, created_at) VALUES (?, ?, ?, ?, ?)",
                [(title, description, reward, index, datetime.now(timezone.utc).isoformat()) for index, (title, description, reward) in enumerate(seed_tasks, start=1)],
            )
        admin = connection.execute("SELECT id, password_hash FROM clients WHERE mobile = ?", (ADMIN_MOBILE,)).fetchone()
        if not admin:
            connection.execute(
                "INSERT INTO clients (name, mobile, password_hash, role, status, joined_at) VALUES (?, ?, ?, ?, ?, ?)",
                (ADMIN_NAME, ADMIN_MOBILE, password_hash("admin123"), "admin", "Active", datetime.now(timezone.utc).isoformat()),
            )
        elif len(admin["password_hash"]) == 64:
            connection.execute("UPDATE clients SET password_hash = ? WHERE id = ?", (password_hash("admin123"), admin["id"]))

@app.on_event("startup")
async def startup() -> None:
    init_database()

def create_session(client_id: int, role: str) -> str:
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = (client_id, role)
    return token

def require_admin(authorization: str | None) -> None:
    token = authorization.removeprefix("Bearer ") if authorization else ""
    if SESSIONS.get(token, (0, ""))[1] != "admin":
        raise HTTPException(status_code=401, detail="Admin login required.")

@app.get("/", response_class=FileResponse)
async def home() -> Path:
    return BASE_DIR / "static" / "index.html"


@app.get("/dashboard", response_class=FileResponse)
async def dashboard_page() -> Path:
    return BASE_DIR / "static" / "dashboard.html"


@app.get("/admin", response_class=FileResponse)
async def admin_page() -> Path:
    return BASE_DIR / "static" / "admin.html"


@app.get("/api/tasks")
async def list_tasks() -> dict[str, list[dict[str, str]]]:
    return {"tasks": TASKS}

@app.post("/api/signup")
async def signup(name: str = Form(...), mobile: str = Form(...), password: str = Form(...)) -> dict[str, str | int]:
    clean_name, clean_mobile = name.strip(), mobile.strip()
    if not clean_name or not clean_mobile:
        raise HTTPException(status_code=400, detail="Name and mobile number are required.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    try:
        with connect_db() as connection:
            cursor = connection.execute(
                "INSERT INTO clients (name, mobile, password_hash, balance, joined_at) VALUES (?, ?, ?, 0, ?) RETURNING id",
                (clean_name, clean_mobile, password_hash(password), datetime.now(timezone.utc).isoformat()),
            )
            client_id = cursor.fetchone()["id"]
    except INTEGRITY_ERRORS:
        raise HTTPException(status_code=409, detail="This mobile number is already registered.") from None
    token = create_session(client_id, "client")
    return {"token": token, "role": "client", "message": f"Welcome, {clean_name}! Your account is ready."}

@app.post("/api/login")
async def login(mobile: str = Form(...), password: str = Form(...)) -> dict[str, str]:
    with connect_db() as connection:
        client = connection.execute("SELECT id, role, password_hash FROM clients WHERE mobile = ?", (mobile.strip(),)).fetchone()
    if not client or not password_matches(password, client["password_hash"]):
        raise HTTPException(status_code=401, detail="Mobile number or password is incorrect.")
    return {"token": create_session(client["id"], client["role"]), "role": client["role"], "message": "Login successful."}

@app.get("/api/me")
async def current_user(authorization: str | None = Header(default=None)) -> dict[str, str | int]:
    token = authorization.removeprefix("Bearer ") if authorization else ""
    client_id, role = SESSIONS.get(token, (0, ""))
    if not client_id:
        raise HTTPException(status_code=401, detail="Login required.")
    with connect_db() as connection:
        client = connection.execute("SELECT id, name, mobile, role, status, balance, bank_details FROM clients WHERE id = ?", (client_id,)).fetchone()
    return dict(client) if client else {"id": client_id, "role": role}


def require_client(authorization: str | None) -> int:
    token = authorization.removeprefix("Bearer ") if authorization else ""
    client_id, role = SESSIONS.get(token, (0, ""))
    if not client_id or role != "client":
        raise HTTPException(status_code=401, detail="Client login required.")
    return client_id


@app.get("/api/config")
async def public_config() -> dict[str, str | int]:
    return {"admin_name": ADMIN_NAME, "admin_mobile": ADMIN_MOBILE, "minimum_withdrawal": 100}


@app.get("/api/dashboard")
async def client_dashboard(authorization: str | None = Header(default=None)) -> dict[str, object]:
    client_id = require_client(authorization)
    with connect_db() as connection:
        client = connection.execute("SELECT id, name, mobile, balance, bank_details FROM clients WHERE id = ?", (client_id,)).fetchone()
        tasks = connection.execute(
            """SELECT t.id, t.title, t.description, t.reward, t.sort_order, t.status,
               CASE WHEN ct.task_id IS NULL THEN 0 ELSE 1 END AS completed
               FROM tasks t LEFT JOIN client_tasks ct ON ct.task_id = t.id AND ct.client_id = ?
               WHERE t.status = 'active' ORDER BY t.sort_order ASC""",
            (client_id,),
        ).fetchall()
        withdrawals = connection.execute(
            "SELECT id, amount, bank_details, status, created_at, completed_at FROM withdrawals WHERE client_id = ? ORDER BY id DESC",
            (client_id,),
        ).fetchall()
    next_task_id = next((task["id"] for task in tasks if not task["completed"]), None)
    task_list = []
    for task in tasks:
        item = dict(task)
        item["progress"] = "Completed" if item.pop("completed") else ("Current" if task["id"] == next_task_id else "Upcoming")
        task_list.append(item)
    return {"client": dict(client), "tasks": task_list, "withdrawals": [dict(item) for item in withdrawals], "admin_name": ADMIN_NAME, "admin_mobile": ADMIN_MOBILE, "minimum_withdrawal": 100}


@app.post("/api/tasks/{task_id}/complete")
async def complete_task(task_id: int, authorization: str | None = Header(default=None)) -> dict[str, str | int]:
    client_id = require_client(authorization)
    with connect_db() as connection:
        task = connection.execute("SELECT id, reward, sort_order, status FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if not task or task["status"] != "active":
            raise HTTPException(status_code=404, detail="Task not found.")
        earlier = connection.execute(
            """SELECT t.id FROM tasks t LEFT JOIN client_tasks ct ON ct.task_id = t.id AND ct.client_id = ?
               WHERE t.status = 'active' AND t.sort_order < ? AND ct.task_id IS NULL LIMIT 1""",
            (client_id, task["sort_order"]),
        ).fetchone()
        if earlier:
            raise HTTPException(status_code=409, detail="Complete the earlier task first.")
        try:
            connection.execute("INSERT INTO client_tasks (client_id, task_id, completed_at) VALUES (?, ?, ?)", (client_id, task_id, datetime.now(timezone.utc).isoformat()))
        except INTEGRITY_ERRORS:
            raise HTTPException(status_code=409, detail="This task is already completed.") from None
        connection.execute("UPDATE clients SET balance = balance + ?, total_earned = total_earned + ?, tasks_completed = tasks_completed + 1 WHERE id = ?", (task["reward"], task["reward"], client_id))
    return {"message": "Task completed and reward added.", "reward": task["reward"]}


@app.post("/api/withdrawals")
async def request_withdrawal(amount: int = Form(...), bank_details: str = Form(...), authorization: str | None = Header(default=None)) -> dict[str, str | int]:
    client_id = require_client(authorization)
    if amount < 100:
        raise HTTPException(status_code=400, detail="Minimum withdrawal amount is Rs 100.")
    if not bank_details.strip():
        raise HTTPException(status_code=400, detail="Bank details are required.")
    with connect_db() as connection:
        client = connection.execute("SELECT balance FROM clients WHERE id = ?", (client_id,)).fetchone()
        if amount > client["balance"]:
            raise HTTPException(status_code=400, detail="Withdrawal amount is higher than your balance.")
        connection.execute("UPDATE clients SET balance = balance - ?, bank_details = ? WHERE id = ?", (amount, bank_details.strip(), client_id))
        cursor = connection.execute(
            "INSERT INTO withdrawals (client_id, amount, bank_details, created_at) VALUES (?, ?, ?, ?) RETURNING id",
            (client_id, amount, bank_details.strip(), datetime.now(timezone.utc).isoformat()),
        )
    return {"message": "Withdrawal is pending admin verification.", "withdrawal_id": cursor.fetchone()["id"], "status": "Pending"}

@app.get("/api/admin/clients")
async def admin_clients(authorization: str | None = Header(default=None)) -> dict[str, list[dict[str, str | int]]]:
    require_admin(authorization)
    with connect_db() as connection:
        clients = connection.execute(
            "SELECT id, name, mobile, status, balance, tasks_completed, total_earned, joined_at FROM clients WHERE role = 'client' ORDER BY id DESC"
        ).fetchall()
    return {"clients": [dict(client) for client in clients]}


@app.post("/api/admin/clients/{client_id}/wallet")
async def update_client_wallet(
    client_id: int,
    action: str = Form(...),
    amount: int = Form(...),
    authorization: str | None = Header(default=None),
) -> dict[str, str | int]:
    require_admin(authorization)
    if action not in ("add", "subtract"):
        raise HTTPException(status_code=400, detail="Action must be 'add' or 'subtract'.")
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero.")
    delta = amount if action == "add" else -amount
    with connect_db() as connection:
        client = connection.execute("SELECT id, name, balance FROM clients WHERE id = ? AND role = 'client'", (client_id,)).fetchone()
        if not client:
            raise HTTPException(status_code=404, detail="Client not found.")
        if delta < 0 and client["balance"] < amount:
            raise HTTPException(status_code=400, detail="Cannot subtract more than the current wallet balance.")
        connection.execute("UPDATE clients SET balance = balance + ? WHERE id = ?", (delta, client_id))
        updated = connection.execute("SELECT balance FROM clients WHERE id = ?", (client_id,)).fetchone()
    verb = "Added" if action == "add" else "Subtracted"
    return {"message": f"{verb} Rs {amount}. New wallet balance is Rs {updated['balance']}.", "balance": updated["balance"]}


@app.post("/api/admin/tasks")
async def create_task(
    title: str = Form(...),
    description: str = Form(...),
    reward: int = Form(...),
    authorization: str | None = Header(default=None),
) -> dict[str, str | int]:
    require_admin(authorization)
    if reward <= 0 or not title.strip() or not description.strip():
        raise HTTPException(status_code=400, detail="Task title, instructions, and a positive reward are required.")
    with connect_db() as connection:
        next_order = connection.execute("SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM tasks").fetchone()["next_order"]
        cursor = connection.execute(
            "INSERT INTO tasks (title, description, reward, sort_order, created_at) VALUES (?, ?, ?, ?, ?) RETURNING id",
            (title.strip(), description.strip(), reward, next_order, datetime.now(timezone.utc).isoformat()),
        )
    return {"id": cursor.fetchone()["id"], "message": "Task created as upcoming."}


@app.get("/api/admin/withdrawals")
async def admin_withdrawals(authorization: str | None = Header(default=None)) -> dict[str, list[dict[str, object]]]:
    require_admin(authorization)
    with connect_db() as connection:
        withdrawals = connection.execute(
            """SELECT w.id, w.amount, w.bank_details, w.status, w.created_at, w.completed_at,
               c.id AS client_id, c.name AS client_name, c.mobile AS client_mobile
               FROM withdrawals w JOIN clients c ON c.id = w.client_id ORDER BY w.id DESC"""
        ).fetchall()
    return {"withdrawals": [dict(item) for item in withdrawals]}


@app.post("/api/admin/withdrawals/{withdrawal_id}/complete")
async def complete_withdrawal(withdrawal_id: int, authorization: str | None = Header(default=None)) -> dict[str, str]:
    require_admin(authorization)
    with connect_db() as connection:
        withdrawal = connection.execute("SELECT status FROM withdrawals WHERE id = ?", (withdrawal_id,)).fetchone()
        if not withdrawal:
            raise HTTPException(status_code=404, detail="Withdrawal request not found.")
        if withdrawal["status"] != "Pending":
            raise HTTPException(status_code=409, detail="This withdrawal is already processed.")
        connection.execute("UPDATE withdrawals SET status = 'Completed', completed_at = ? WHERE id = ?", (datetime.now(timezone.utc).isoformat(), withdrawal_id))
    return {"message": "Withdrawal marked as completed and paid."}

