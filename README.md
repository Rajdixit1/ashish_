# HS Task Group

A FastAPI clone of the HS Task Group task-earning landing page. It includes SQLite-backed signup/login, a sequential post-login task dashboard, a zero-balance wallet, pending withdrawals, and a protected admin panel.

## Run locally

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

Open <http://127.0.0.1:8000> in a browser.

Client dashboard: <http://127.0.0.1:8000/dashboard>

Admin panel: <http://127.0.0.1:8000/admin>

Default admin login:

- Mobile: `9999999999`
- Password: `admin123`

Client records are stored in `hstaskgroup.db`. The `/api/tasks`, `/api/signup`, `/api/login`, and `/api/admin/clients` endpoints are available for the frontend. Production use should move sessions to a durable store and put secrets in environment variables.

New accounts start with a Rs 0 balance. Tasks must be completed in order, and withdrawals require at least Rs 100. Each withdrawal appears in the admin queue as Pending until the admin verifies payment and marks it Completed.

From the admin panel, every client wallet can be topped up or deducted from using the Wallet column: `POST /api/admin/clients/{client_id}/wallet` with form fields `action` (`add` or `subtract`) and a positive `amount`. The balance is never allowed to go below Rs 0.

## Neon PostgreSQL deployment

The app uses SQLite locally and switches to Neon PostgreSQL automatically when `DATABASE_URL` is set. Create a Neon project, copy its pooled connection string, and add it to Render as the `DATABASE_URL` environment variable. The included `render.yaml` contains the Render build and start commands.
