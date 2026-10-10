# MediRecord — Patient Health Record Management System

A DBMS mini-project: a hospital application with **four login roles** —
**Patient**, **Doctor**, **Lab Assistant**, and **Admin** — built on
**Flask (Python)** + **PostgreSQL**, deployable to **Vercel** with a free
**Neon** Postgres database.

---

## 1. Features

| Role | Capabilities |
|---|---|
| **Patient** | Register/login, book & cancel appointments, view medical records (diagnosis/prescription), view & download lab reports, edit contact profile |
| **Doctor** | View today's appointments, look up any patient, add diagnosis + prescription, request lab tests, view lab results |
| **Lab Assistant** | View the pending lab-test queue, upload results (text summary + optional PDF/image), view own upload history |
| **Admin** | Create/deactivate Doctor and Lab Assistant accounts, manage Departments, view all Patients/Appointments, dashboard stats |

## 2. DBMS concepts demonstrated

- **Normalized schema (BCNF)** — see [`database/schema.sql`](database/schema.sql): `users` (auth) is separated from role-specific profile tables (`patients`, `doctors`, `lab_assistants`, `admins`), all linked by foreign keys.
- **Constraints** — `PRIMARY KEY`, `FOREIGN KEY` with `ON DELETE CASCADE`/`SET NULL`, `CHECK`, `UNIQUE`, `NOT NULL`.
- **Trigger** — inserting a `lab_reports` row automatically flips the linked `lab_tests.status` to `Completed` (`trg_lab_report_insert`).
- **Views** — `view_patient_history`, `view_doctor_schedule`, `view_pending_lab_tests`, `view_admin_stats` (multi-table joins used directly by the app and report).
- **Stored procedures & functions** — `sp_book_appointment` (past-date, inactive-doctor and slot-clash validation), `sp_complete_visit` (atomic visit completion), `fn_patient_age`, `fn_doctor_load`: see [`database/advanced_features.sql`](database/advanced_features.sql). A second trigger, `trg_medical_record_audit`, logs every medical-record change to `audit_log`.
- **Transactions** — COMMIT, ROLLBACK, SAVEPOINT and automatic rollback demos with ACID notes: [`database/transactions.sql`](database/transactions.sql).
- **Queries** — joins, aggregates, subqueries, indexes: see [`database/queries.sql`](database/queries.sql) for a ready-to-run demo set for your project report / viva.
- **BLOB storage** — lab report files are stored as `BYTEA` directly in Postgres (not on disk), so the app has zero filesystem dependency — required for serverless hosting.

## 3. Tech stack

- **Backend:** Flask 3, plain `psycopg2` (raw parameterized SQL — no ORM, so every query is visible)
- **Auth:** `werkzeug.security` password hashing (scrypt), Flask sessions, role-based route decorators
- **Frontend:** Jinja2 templates + Bootstrap 5 (CDN)
- **Database:** PostgreSQL (Neon for the hosted deployment)
- **Hosting:** Vercel (serverless Python)

## 4. Project structure

```
dbs prject/
├── app.py                 # Flask app factory, blueprint registration
├── auth.py                 # Login/Register/Logout + role_required decorator
├── db.py                   # psycopg2 connection helper
├── config.py                # Reads SECRET_KEY / DATABASE_URL from env
├── patient_routes.py        # /patient/*
├── doctor_routes.py         # /doctor/*
├── lab_routes.py            # /lab/*
├── admin_routes.py          # /admin/*
├── database/
│   ├── schema.sql           # DDL: tables, constraints, indexes, trigger, views
│   ├── advanced_features.sql # Procedures, functions, audit trigger
│   ├── seed_data.sql        # Demo accounts + sample records
│   ├── bulk_demo_data.sql   # 14 patients, 6 doctors, 48 appointments, ...
│   ├── queries.sql          # Demo SQL for the project report
│   └── transactions.sql     # COMMIT / ROLLBACK / SAVEPOINT demo
├── templates/                # Jinja2 HTML (per role)
├── static/css/style.css
├── api/index.py              # Vercel serverless entrypoint
├── vercel.json
└── requirements.txt
```

---

## 5. Run it locally (for development / viva demo)

### 5.1 Create the database

You have pgAdmin4 installed, so the easiest path:

1. Open **pgAdmin4** → right-click **Databases** → **Create** → **Database** → name it `health_records`.
2. Open the **Query Tool** on that database, open and run, in order: [`schema.sql`](database/schema.sql), [`advanced_features.sql`](database/advanced_features.sql), [`seed_data.sql`](database/seed_data.sql), then [`bulk_demo_data.sql`](database/bulk_demo_data.sql).

(Equivalently from a terminal: `psql -U postgres -c "CREATE DATABASE health_records;"` then `psql -U postgres -d health_records -f database/schema.sql -f database/advanced_features.sql -f database/seed_data.sql -f database/bulk_demo_data.sql`.)

### 5.2 Install dependencies

```bash
cd "~/Desktop/dbs prject"
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 5.3 Set environment variables

```bash
export DATABASE_URL="postgresql://postgres:YOUR_PASSWORD@localhost:5432/health_records?sslmode=disable"
export SECRET_KEY="any-random-string"
```

### 5.4 Run

```bash
python3 app.py
```

Open **http://127.0.0.1:5000**.

### 5.5 Demo logins (from `seed_data.sql`)

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| Doctor | `drmehta` | `doctor123` |
| Lab Assistant | `labtech` | `lab123` |
| Patient | `rahul` | `patient123` |

---

## 6. Deploy to Vercel (public URL) with Neon Postgres

Vercel doesn't host a database itself, so we pair it with **Neon** — a free
serverless Postgres that's the standard match for Vercel deployments.

### 6.1 Create the database on Neon

1. Go to **neon.tech** and sign up (free tier).
2. Create a new project → it gives you a **connection string** that looks like:
   `postgresql://user:password@ep-xxxx.region.aws.neon.tech/neondb?sslmode=require`
3. Open Neon's **SQL Editor** (or connect via pgAdmin4 using that connection string) and run the same four scripts in the same order — same as the local setup, just against this remote DB.

### 6.2 Push the project to GitHub

Vercel deploys from a Git repo:

```bash
cd "~/Desktop/dbs prject"
git init
git add .
git commit -m "Initial commit: MediRecord DBMS project"
```

Then create a new repository on GitHub and push:

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

### 6.3 Deploy on Vercel

1. Go to **vercel.com**, sign up/log in, click **Add New → Project**, and import the GitHub repo you just pushed.
2. In **Environment Variables**, add:
   - `DATABASE_URL` = the Neon connection string from step 6.1
   - `SECRET_KEY` = any random string
3. Click **Deploy**. Vercel auto-detects the Python app via `vercel.json` + `api/index.py`.
4. Once done, you'll get a public URL like `https://your-project.vercel.app`.

That's it — the same app, publicly reachable, backed by Neon Postgres.

---

## 7. Automated tests

[`test_app.py`](test_app.py) drives the real app through CRUD for all four roles and the edge cases (appointment clash, past dates, invalid file type, wrong role, inactive doctor, duplicate username). It writes data, so point it at a disposable database loaded with the four scripts:

```bash
DATABASE_URL="postgresql://postgres:YOUR_PASSWORD@localhost:5432/health_records_test?sslmode=disable" python3 test_app.py
```

## 8. Notes for your project report

- Run the queries in `database/queries.sql` in pgAdmin4 against your database to screenshot joins, aggregates, subqueries, and the trigger in action — useful evidence for the DBMS report/viva.
- The ER diagram maps directly to `database/schema.sql`: `users` 1—1 with each of `patients`/`doctors`/`lab_assistants`/`admins`; `patients` 1—N `appointments` N—1 `doctors`; `appointments`/`patients`/`doctors` 1—N `medical_records`; `patients`/`doctors` 1—N `lab_tests` 1—1 `lab_reports`; `departments` 1—N `doctors`.
- Password hashing (scrypt via Werkzeug) and parameterized SQL throughout (`psycopg2` with `%s` placeholders) are worth calling out if the evaluator asks about security.
