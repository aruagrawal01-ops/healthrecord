# MediRecord — Patient Health Record Management System

A DBMS mini-project: a hospital application with **four login roles** —
**Patient**, **Doctor**, **Lab Assistant**, and **Admin** — built on
**Flask (Python)** + **PostgreSQL**, deployable to **Vercel** with a free
**Neon** Postgres database.

---

## 1. Features

| Role | Capabilities |
|---|---|
| **Patient** | Register/login; book with a **live slot picker** (free/booked slots from `fn_free_slots`); **reschedule** atomically; cancel; health-trend charts of BP, pulse and weight; record timeline with search and department filters; **printable visit summaries**; lab reports with download; profile |
| **Doctor** | Dashboard with today's clinic timeline and weekly activity charts; **weekly calendar**; filterable appointments; patient list and hospital-wide search; patient view with vitals charts; diagnosis + prescription + **vitals** (via `sp_complete_visit`); lab requests with common-test picker |
| **Lab Assistant** | Dashboard with turnaround and workload charts; pending queue colour-coded by age with filters; file upload (stored as BYTEA); searchable upload history with turnaround times |
| **Admin** | Analytics dashboard (KPIs, monthly trend, department load, demographics); **Reports & Analytics** with CSV exports; filterable appointment management; patient/doctor/lab-staff management (edit, activate/deactivate, **reset password**); departments (add, rename, delete); **announcements** to any role; audit log with filters; **Database Explorer** with table browser and a **read-only SQL console** |
| **Everyone** | Light/dark theme, responsive sidebar layout, toast notifications, sortable/searchable tables, change password |

**Sample data:** 80 patients, 20 doctors across 10 clinical departments, 4 lab staff, about 2,200 appointments over six months (plus three weeks ahead), 1,700+ medical records with vitals, 880+ lab tests. Generated deterministically by `bulk_demo_data.sql`, dated relative to the day it runs.

**Demo logins:** `admin`/`admin123`, `drmehta`/`doctor123` (any `dr...` doctor uses `doctor123`), `labtech`/`lab123`, `rahul`/`patient123` (any generated patient, e.g. `ananya.iyer`, uses `patient123`).

## 2. DBMS concepts demonstrated

- **Normalized schema (BCNF)** — see [`database/schema.sql`](database/schema.sql): `users` (auth) is separated from role-specific profile tables (`patients`, `doctors`, `lab_assistants`, `admins`), all linked by foreign keys.
- **Constraints** — `PRIMARY KEY`, `FOREIGN KEY` with `ON DELETE CASCADE`/`SET NULL`, `CHECK`, `UNIQUE`, `NOT NULL`.
- **Trigger** — inserting a `lab_reports` row automatically flips the linked `lab_tests.status` to `Completed` (`trg_lab_report_insert`).
- **Views** — `view_patient_history`, `view_doctor_schedule`, `view_pending_lab_tests`, `view_admin_stats`, `view_doctor_performance`, `view_department_stats` (multi-table joins and `FILTER` aggregates used directly by the dashboards and reports).
- **Stored procedures & functions** — `sp_book_appointment` (past date, Sunday, clinic hours, inactive doctor and slot-clash validation), `sp_complete_visit` (atomic visit completion with vitals), `sp_reschedule_appointment` (cancel + rebook in one transaction), `fn_patient_age`, `fn_doctor_load`, `fn_free_slots` (set-returning): see [`database/advanced_features.sql`](database/advanced_features.sql). A second trigger, `trg_medical_record_audit`, logs every medical-record change to `audit_log`.
- **Transactions** — COMMIT, ROLLBACK, SAVEPOINT and automatic rollback demos with ACID notes: [`database/transactions.sql`](database/transactions.sql).
- **Queries** — joins, aggregates, subqueries, indexes: see [`database/queries.sql`](database/queries.sql) for a ready-to-run demo set for your project report / viva.
- **BLOB storage** — lab report files are stored as `BYTEA` directly in Postgres (not on disk), so the app has zero filesystem dependency — required for serverless hosting.

## 3. Tech stack

- **Backend:** Flask 3, `pg8000` (pure-Python driver; raw parameterized SQL — no ORM, so every query is visible)
- **Auth:** `werkzeug.security` password hashing (scrypt), Flask sessions, role-based route decorators
- **Frontend:** Jinja2 templates, Bootstrap 5, Chart.js and a custom design system (`static/css/style.css`, `static/js/app.js`)
- **Database:** PostgreSQL (Neon for the hosted deployment)
- **Hosting:** Vercel (serverless Python)

## 4. Project structure

```
dbs prject/
├── app.py                 # Flask app factory, blueprint registration
├── auth.py                 # Login/Register/Logout/Change password + role_required decorator
├── db.py                   # pg8000 connection helper (IST session, rollback on error)
├── config.py                # Reads SECRET_KEY / DATABASE_URL from env
├── patient_routes.py        # /patient/*
├── doctor_routes.py         # /doctor/*
├── lab_routes.py            # /lab/*
├── admin_routes.py          # /admin/* (dashboard, reports, CSV, database explorer)
├── test_app.py              # End-to-end checks (CRUD, edge cases, transactions)
├── database/
│   ├── schema.sql           # DDL: tables, constraints, indexes, trigger, views
│   ├── advanced_features.sql # Procedures, functions, audit trigger
│   ├── seed_data.sql        # Demo accounts + sample records
│   ├── bulk_demo_data.sql   # 80 patients, 20 doctors, ~2,200 appointments, vitals, labs
│   ├── queries.sql          # Demo SQL for the project report
│   └── transactions.sql     # COMMIT / ROLLBACK / SAVEPOINT demo
├── templates/                # Jinja2 HTML (per role)
├── static/css/style.css     # Design system (light + dark)
├── static/js/app.js         # Slot picker, charts, table tools, toasts, theme
└── requirements.txt          # Vercel detects app.py as the Flask entrypoint
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
3. Open Neon's **SQL Editor** (or connect via pgAdmin4 using that connection string) and run the same four scripts in the same order — same as the local setup. The app sets each session to Indian time (`Asia/Kolkata`), so "today" matches the hospital's clock even though Neon runs in UTC, just against this remote DB.

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
3. Click **Deploy**. Vercel auto-detects the Flask app from `app.py`.
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
- Password hashing (scrypt via Werkzeug) and parameterized SQL throughout (`pg8000` with `%s` placeholders) are worth calling out if the evaluator asks about security.
