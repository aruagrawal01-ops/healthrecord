import csv
import io
import re
import time

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from auth import role_required
from db import DatabaseError, error_message, execute, get_db, query_all, query_one, today
from patient_routes import vitals_series

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ---------------------------------------------------------------- helpers
def csv_response(rows, filename):
    out = io.StringIO()
    writer = csv.writer(out)
    if rows:
        writer.writerow(rows[0].keys())
        writer.writerows([[("" if v is None else v) for v in r.values()] for r in rows])
    return Response(out.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})


def series(rows, label_key, *value_keys):
    """Turn query rows into {labels: [...], key: [...]} for Chart.js."""
    data = {"labels": [str(r[label_key]) for r in rows]}
    for k in value_keys:
        data[k] = [float(r[k]) if r[k] is not None else 0 for r in rows]
    return data


def _create_staff_account(username, email, password, role):
    existing = query_one(
        "SELECT user_id FROM users WHERE username = %s OR email = %s", (username, email)
    )
    if existing:
        return None
    if len(password) < 6:
        return None
    user = execute(
        "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s) RETURNING user_id",
        (username, email, generate_password_hash(password), role),
    )
    return user["user_id"]


# ---------------------------------------------------------------- dashboard
@admin_bp.route("/dashboard")
@role_required("admin")
def dashboard():
    stats = query_one("SELECT * FROM view_admin_stats")
    kpi = query_one(
        """SELECT
               ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'Completed') / NULLIF(COUNT(*) FILTER (WHERE status <> 'Scheduled'), 0), 1) AS completion_rate,
               ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'Cancelled') / NULLIF(COUNT(*), 0), 1) AS cancel_rate,
               COUNT(*) FILTER (WHERE appointment_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 6 AND status = 'Scheduled') AS next_week
           FROM appointments WHERE appointment_date >= CURRENT_DATE - 30"""
    )
    kpi["avg_turnaround"] = query_one(
        """SELECT ROUND(AVG(EXTRACT(EPOCH FROM lr.uploaded_at - lt.requested_at) / 3600)::numeric, 1) AS h
           FROM lab_reports lr JOIN lab_tests lt ON lt.lab_test_id = lr.lab_test_id"""
    )["h"]
    monthly = query_all(
        """SELECT to_char(date_trunc('month', appointment_date), 'Mon YY') AS month,
                  COUNT(*) FILTER (WHERE status = 'Completed') AS completed,
                  COUNT(*) FILTER (WHERE status = 'Cancelled') AS cancelled,
                  COUNT(*) FILTER (WHERE status = 'Scheduled') AS scheduled
           FROM appointments GROUP BY date_trunc('month', appointment_date) ORDER BY date_trunc('month', appointment_date)"""
    )
    depts = query_all("SELECT department, appointments FROM view_department_stats WHERE appointments > 0 ORDER BY appointments DESC")
    ages = query_all(
        """SELECT band, COUNT(*) AS n FROM (
               SELECT CASE WHEN fn_patient_age(dob) < 13 THEN '0-12' WHEN fn_patient_age(dob) < 18 THEN '13-17'
                           WHEN fn_patient_age(dob) < 35 THEN '18-34' WHEN fn_patient_age(dob) < 50 THEN '35-49'
                           WHEN fn_patient_age(dob) < 65 THEN '50-64' ELSE '65+' END AS band
               FROM patients) b
           GROUP BY band ORDER BY MIN(band)"""
    )
    status_split = query_all("SELECT status, COUNT(*) AS n FROM appointments GROUP BY status ORDER BY n DESC")
    top_doctors = query_all("SELECT * FROM view_doctor_performance ORDER BY completed DESC LIMIT 5")
    todays = query_all(
        """SELECT a.appointment_time, a.status, p.full_name AS patient_name, d.full_name AS doctor_name, dep.name AS department
           FROM appointments a JOIN patients p ON a.patient_id = p.patient_id JOIN doctors d ON a.doctor_id = d.doctor_id
           LEFT JOIN departments dep ON dep.department_id = d.department_id
           WHERE a.appointment_date = CURRENT_DATE ORDER BY a.appointment_time LIMIT 8"""
    )
    audit = query_all("SELECT * FROM audit_log ORDER BY changed_at DESC, log_id DESC LIMIT 5")
    return render_template(
        "admin/dashboard.html", stats=stats, kpi=kpi, top_doctors=top_doctors, todays=todays, audit=audit, today=today(),
        monthly=series(monthly, "month", "completed", "cancelled", "scheduled"), depts=series(depts, "department", "appointments"),
        ages=series(ages, "band", "n"), status_split=series(status_split, "status", "n"),
    )


# ---------------------------------------------------------------- reports
@admin_bp.route("/reports")
@role_required("admin")
def reports():
    departments = query_all("SELECT * FROM view_department_stats ORDER BY appointments DESC")
    doctors = query_all("SELECT * FROM view_doctor_performance ORDER BY completed DESC")
    lab = query_all(
        """SELECT lt.test_name, COUNT(*) AS ordered, COUNT(lr.report_id) AS reported,
                  ROUND(AVG(EXTRACT(EPOCH FROM lr.uploaded_at - lt.requested_at) / 3600)::numeric, 1) AS avg_hours
           FROM lab_tests lt LEFT JOIN lab_reports lr ON lr.lab_test_id = lt.lab_test_id
           GROUP BY lt.test_name ORDER BY ordered DESC"""
    )
    ageing = query_all(
        """SELECT bucket, COUNT(*) AS n FROM (
               SELECT CASE WHEN CURRENT_DATE - requested_at::date <= 1 THEN '0-1 days'
                           WHEN CURRENT_DATE - requested_at::date <= 3 THEN '2-3 days'
                           WHEN CURRENT_DATE - requested_at::date <= 7 THEN '4-7 days' ELSE 'Over 7 days' END AS bucket,
                      CURRENT_DATE - requested_at::date AS d
               FROM lab_tests WHERE status = 'Pending') x
           GROUP BY bucket ORDER BY MIN(d)"""
    )
    blood = query_all("SELECT COALESCE(NULLIF(blood_group, ''), 'Unknown') AS blood_group, COUNT(*) AS n FROM patients GROUP BY 1 ORDER BY n DESC")
    gender = query_all("SELECT gender, COUNT(*) AS n FROM patients GROUP BY gender ORDER BY n DESC")
    diagnoses = query_all("SELECT diagnosis, COUNT(*) AS n FROM medical_records GROUP BY diagnosis ORDER BY n DESC LIMIT 10")
    weekday = query_all(
        """SELECT to_char(appointment_date, 'Dy') AS day, COUNT(*) AS n FROM appointments
           WHERE status <> 'Cancelled' GROUP BY to_char(appointment_date, 'Dy'), EXTRACT(ISODOW FROM appointment_date)
           ORDER BY EXTRACT(ISODOW FROM appointment_date)"""
    )
    hours = query_all(
        """SELECT to_char(appointment_time, 'HH24:MI') AS slot, COUNT(*) AS n FROM appointments
           WHERE status <> 'Cancelled' GROUP BY appointment_time ORDER BY appointment_time"""
    )
    return render_template(
        "admin/reports.html", departments=departments, doctors=doctors, lab=lab, diagnoses=diagnoses,
        dept_chart=series(departments, "department", "appointments", "completed"),
        ageing=series(ageing, "bucket", "n"), blood=series(blood, "blood_group", "n"), gender=series(gender, "gender", "n"),
        weekday=series(weekday, "day", "n"), hours=series(hours, "slot", "n"),
    )


@admin_bp.route("/export/<name>.csv")
@role_required("admin")
def export(name):
    queries = {
        "departments": "SELECT * FROM view_department_stats ORDER BY department",
        "doctors": "SELECT * FROM view_doctor_performance ORDER BY doctor_name",
        "lab-tests": """SELECT lt.lab_test_id, p.full_name AS patient, d.full_name AS doctor, lt.test_name, lt.status, lt.requested_at,
                               lr.uploaded_at, lr.result_summary
                        FROM lab_tests lt JOIN patients p ON p.patient_id = lt.patient_id JOIN doctors d ON d.doctor_id = lt.doctor_id
                        LEFT JOIN lab_reports lr ON lr.lab_test_id = lt.lab_test_id ORDER BY lt.requested_at DESC""",
        "patients": """SELECT p.patient_id, p.full_name, u.username, u.email, p.gender, p.dob, fn_patient_age(p.dob) AS age, p.blood_group,
                              p.phone, p.address, u.is_active FROM patients p JOIN users u ON u.user_id = p.user_id ORDER BY p.full_name""",
        "audit-log": "SELECT * FROM audit_log ORDER BY changed_at DESC",
    }
    if name == "appointments":
        sql, params = _appointment_filter_sql()
        return csv_response(query_all(sql, params), "appointments.csv")
    if name not in queries:
        abort(404)
    return csv_response(query_all(queries[name]), f"{name}.csv")


# ---------------------------------------------------------------- appointments
def _appointment_filter_sql(limit=None):
    sql = """SELECT a.appointment_id, a.appointment_date, a.appointment_time, a.status, a.reason,
                    p.full_name AS patient_name, d.full_name AS doctor_name, dep.name AS department
             FROM appointments a
             JOIN patients p ON a.patient_id = p.patient_id
             JOIN doctors d ON a.doctor_id = d.doctor_id
             LEFT JOIN departments dep ON dep.department_id = d.department_id
             WHERE 1 = 1"""
    params = []
    f = request.args
    if f.get("status"):
        sql += " AND a.status = %s"
        params.append(f["status"])
    if f.get("department"):
        sql += " AND dep.department_id = %s"
        params.append(f["department"])
    if f.get("doctor"):
        sql += " AND d.doctor_id = %s"
        params.append(f["doctor"])
    if f.get("from"):
        sql += " AND a.appointment_date >= %s"
        params.append(f["from"])
    if f.get("to"):
        sql += " AND a.appointment_date <= %s"
        params.append(f["to"])
    if f.get("q"):
        sql += " AND p.full_name ILIKE %s"
        params.append(f"%{f['q'].strip()}%")
    sql += " ORDER BY a.appointment_date DESC, a.appointment_time DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return sql, params


@admin_bp.route("/appointments")
@role_required("admin")
def appointments():
    sql, params = _appointment_filter_sql(limit=400)
    rows = query_all(sql, params)
    count_sql, count_params = _appointment_filter_sql()
    counts = query_one(
        f"""SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status = 'Scheduled') AS scheduled,
                   COUNT(*) FILTER (WHERE status = 'Completed') AS completed, COUNT(*) FILTER (WHERE status = 'Cancelled') AS cancelled
            FROM ({count_sql}) f""",
        count_params,
    )
    return render_template(
        "admin/appointments.html", appointments=rows, counts=counts, filters=request.args,
        departments=query_all("SELECT department_id, name FROM departments ORDER BY name"),
        doctors=query_all("SELECT doctor_id, full_name FROM doctors ORDER BY full_name"),
    )


@admin_bp.route("/appointments/<int:appointment_id>/cancel", methods=["POST"])
@role_required("admin")
def cancel_appointment(appointment_id):
    execute("UPDATE appointments SET status = 'Cancelled' WHERE appointment_id = %s AND status = 'Scheduled'", (appointment_id,))
    flash("Appointment cancelled.", "info")
    return redirect(request.form.get("back") if request.form.get("back", "").startswith("/admin/") else url_for("admin.appointments"))


# ---------------------------------------------------------------- doctors
@admin_bp.route("/doctors", methods=["GET", "POST"])
@role_required("admin")
def doctors():
    if request.method == "POST":
        user_id = _create_staff_account(
            request.form["username"].strip(),
            request.form["email"].strip(),
            request.form["password"],
            "doctor",
        )
        if user_id is None:
            flash("That username or email is already registered, or the password is under 6 characters.", "danger")
        else:
            execute(
                """INSERT INTO doctors (user_id, full_name, specialization, qualification, department_id, phone)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (
                    user_id,
                    request.form["full_name"].strip(),
                    request.form.get("specialization", ""),
                    request.form.get("qualification", ""),
                    request.form.get("department_id") or None,
                    request.form.get("phone", ""),
                ),
            )
            flash("Doctor account created.", "success")
        return redirect(url_for("admin.doctors"))

    rows = query_all(
        """SELECT d.*, u.username, u.email, u.is_active, dep.name AS department,
                  fn_doctor_load(d.doctor_id, CURRENT_DATE) AS todays_load,
                  perf.completed, perf.patients_seen, perf.completion_rate
           FROM doctors d
           JOIN users u ON d.user_id = u.user_id
           LEFT JOIN departments dep ON d.department_id = dep.department_id
           LEFT JOIN view_doctor_performance perf ON perf.doctor_id = d.doctor_id
           ORDER BY dep.name NULLS LAST, d.full_name"""
    )
    departments = query_all("SELECT * FROM departments ORDER BY name")
    return render_template("admin/doctors.html", doctors=rows, departments=departments)


@admin_bp.route("/doctors/<int:doctor_id>/edit", methods=["POST"])
@role_required("admin")
def edit_doctor(doctor_id):
    try:
        execute(
            """UPDATE doctors SET full_name = %s, specialization = %s, qualification = %s, department_id = %s, phone = %s
               WHERE doctor_id = %s""",
            (request.form["full_name"].strip(), request.form.get("specialization", ""), request.form.get("qualification", ""),
             request.form.get("department_id") or None, request.form.get("phone", ""), doctor_id),
        )
        execute("UPDATE users SET email = %s WHERE user_id = (SELECT user_id FROM doctors WHERE doctor_id = %s)",
                (request.form["email"].strip(), doctor_id))
        flash("Doctor details updated.", "success")
    except DatabaseError as e:
        flash(error_message(e), "danger")
    return redirect(url_for("admin.doctors"))


@admin_bp.route("/doctors/<int:doctor_id>/toggle", methods=["POST"])
@role_required("admin")
def toggle_doctor(doctor_id):
    execute(
        """UPDATE users SET is_active = NOT is_active
           WHERE user_id = (SELECT user_id FROM doctors WHERE doctor_id = %s)""",
        (doctor_id,),
    )
    flash("Doctor account status updated.", "info")
    return redirect(url_for("admin.doctors"))


@admin_bp.route("/users/<int:user_id>/password", methods=["POST"])
@role_required("admin")
def reset_password(user_id):
    new = request.form.get("new_password", "")
    if len(new) < 6:
        flash("The new password must be at least 6 characters.", "danger")
    elif user_id == session["user_id"]:
        flash("Use Change Password to update your own password.", "warning")
    else:
        execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (generate_password_hash(new), user_id))
        flash("Password reset. Share the new password with the user securely.", "success")
    back = request.form.get("back", "")
    return redirect(back if back.startswith("/admin/") else url_for("admin.dashboard"))


# ---------------------------------------------------------------- lab assistants
@admin_bp.route("/lab-assistants", methods=["GET", "POST"])
@role_required("admin")
def lab_assistants():
    if request.method == "POST":
        user_id = _create_staff_account(
            request.form["username"].strip(),
            request.form["email"].strip(),
            request.form["password"],
            "lab_assistant",
        )
        if user_id is None:
            flash("That username or email is already registered, or the password is under 6 characters.", "danger")
        else:
            execute(
                "INSERT INTO lab_assistants (user_id, full_name, phone) VALUES (%s, %s, %s)",
                (user_id, request.form["full_name"].strip(), request.form.get("phone", "")),
            )
            flash("Lab assistant account created.", "success")
        return redirect(url_for("admin.lab_assistants"))

    rows = query_all(
        """SELECT la.*, u.username, u.email, u.is_active,
                  COUNT(lr.report_id) AS uploads,
                  ROUND(AVG(EXTRACT(EPOCH FROM lr.uploaded_at - lt.requested_at) / 3600)::numeric, 1) AS avg_hours,
                  MAX(lr.uploaded_at) AS last_upload
           FROM lab_assistants la
           JOIN users u ON la.user_id = u.user_id
           LEFT JOIN lab_reports lr ON lr.lab_assistant_id = la.lab_assistant_id
           LEFT JOIN lab_tests lt ON lt.lab_test_id = lr.lab_test_id
           GROUP BY la.lab_assistant_id, u.username, u.email, u.is_active
           ORDER BY la.full_name"""
    )
    return render_template("admin/lab_assistants.html", lab_assistants=rows)


@admin_bp.route("/lab-assistants/<int:lab_assistant_id>/toggle", methods=["POST"])
@role_required("admin")
def toggle_lab_assistant(lab_assistant_id):
    execute(
        """UPDATE users SET is_active = NOT is_active
           WHERE user_id = (SELECT user_id FROM lab_assistants WHERE lab_assistant_id = %s)""",
        (lab_assistant_id,),
    )
    flash("Lab assistant account status updated.", "info")
    return redirect(url_for("admin.lab_assistants"))


# ---------------------------------------------------------------- departments
@admin_bp.route("/departments", methods=["GET", "POST"])
@role_required("admin")
def departments():
    if request.method == "POST":
        name = request.form["name"].strip()
        existing = query_one("SELECT department_id FROM departments WHERE name = %s", (name,))
        if existing:
            flash("That department already exists.", "danger")
        else:
            execute("INSERT INTO departments (name) VALUES (%s)", (name,))
            flash("Department added.", "success")
        return redirect(url_for("admin.departments"))

    rows = query_all(
        """SELECT s.*, s.doctors AS doctor_count,
                  (SELECT string_agg(d.full_name, ', ' ORDER BY d.full_name) FROM doctors d WHERE d.department_id = s.department_id) AS doctor_names
           FROM view_department_stats s ORDER BY s.department"""
    )
    return render_template("admin/departments.html", departments=rows)


@admin_bp.route("/departments/<int:department_id>/rename", methods=["POST"])
@role_required("admin")
def rename_department(department_id):
    try:
        execute("UPDATE departments SET name = %s WHERE department_id = %s", (request.form["name"].strip(), department_id))
        flash("Department renamed.", "success")
    except DatabaseError as e:
        flash(error_message(e), "danger")
    return redirect(url_for("admin.departments"))


@admin_bp.route("/departments/<int:department_id>/delete", methods=["POST"])
@role_required("admin")
def delete_department(department_id):
    # doctors.department_id is ON DELETE SET NULL, so doctors stay and just lose the department.
    execute("DELETE FROM departments WHERE department_id = %s", (department_id,))
    flash("Department deleted. Its doctors are now unassigned.", "info")
    return redirect(url_for("admin.departments"))


# ---------------------------------------------------------------- patients
@admin_bp.route("/patients")
@role_required("admin")
def patients():
    sql = """SELECT p.*, fn_patient_age(p.dob) AS age, u.username, u.email, u.is_active,
                    COUNT(a.appointment_id) AS visits, MAX(a.appointment_date) FILTER (WHERE a.appointment_date <= CURRENT_DATE) AS last_visit
             FROM patients p JOIN users u ON p.user_id = u.user_id
             LEFT JOIN appointments a ON a.patient_id = p.patient_id WHERE 1 = 1"""
    params = []
    search = request.args.get("q", "").strip()
    if search:
        sql += " AND p.full_name ILIKE %s"
        params.append(f"%{search}%")
    for field in ("gender", "blood_group"):
        if request.args.get(field):
            sql += f" AND p.{field} = %s"
            params.append(request.args[field])
    sql += " GROUP BY p.patient_id, u.username, u.email, u.is_active ORDER BY p.full_name"
    return render_template("admin/patients.html", patients=query_all(sql, params), search=search, filters=request.args)


@admin_bp.route("/patients/<int:patient_id>/toggle", methods=["POST"])
@role_required("admin")
def toggle_patient(patient_id):
    execute("UPDATE users SET is_active = NOT is_active WHERE user_id = (SELECT user_id FROM patients WHERE patient_id = %s)", (patient_id,))
    flash("Patient account status updated.", "info")
    return redirect(url_for("admin.patients"))


@admin_bp.route("/patients/<int:patient_id>")
@role_required("admin")
def patient_detail(patient_id):
    person = query_one(
        """SELECT p.*, fn_patient_age(p.dob) AS age, u.username, u.email, u.is_active, u.user_id FROM patients p
           JOIN users u ON p.user_id = u.user_id WHERE p.patient_id = %s""",
        (patient_id,),
    )
    if person is None:
        abort(404)
    records = query_all(
        """SELECT mr.*, d.full_name AS doctor_name FROM medical_records mr
           JOIN doctors d ON mr.doctor_id = d.doctor_id
           WHERE mr.patient_id = %s ORDER BY mr.created_at DESC""",
        (patient_id,),
    )
    appts = query_all(
        """SELECT a.*, d.full_name AS doctor_name FROM appointments a
           JOIN doctors d ON a.doctor_id = d.doctor_id
           WHERE a.patient_id = %s ORDER BY a.appointment_date DESC""",
        (patient_id,),
    )
    return render_template(
        "admin/patient_detail.html", person=person, records=records, appointments=appts, vitals=vitals_series(patient_id, 15)
    )


# ---------------------------------------------------------------- announcements
@admin_bp.route("/announcements", methods=["GET", "POST"])
@role_required("admin")
def announcements():
    if request.method == "POST":
        execute(
            "INSERT INTO announcements (title, body, audience, is_pinned, created_by) VALUES (%s, %s, %s, %s, %s)",
            (request.form["title"].strip(), request.form["body"].strip(), request.form.get("audience", "all"),
             bool(request.form.get("is_pinned")), session["user_id"]),
        )
        flash("Announcement published.", "success")
        return redirect(url_for("admin.announcements"))
    rows = query_all(
        """SELECT a.*, u.username AS author FROM announcements a LEFT JOIN users u ON u.user_id = a.created_by
           ORDER BY a.is_pinned DESC, a.created_at DESC"""
    )
    return render_template("admin/announcements.html", announcements=rows)


@admin_bp.route("/announcements/<int:announcement_id>/pin", methods=["POST"])
@role_required("admin")
def pin_announcement(announcement_id):
    execute("UPDATE announcements SET is_pinned = NOT is_pinned WHERE announcement_id = %s", (announcement_id,))
    return redirect(url_for("admin.announcements"))


@admin_bp.route("/announcements/<int:announcement_id>/delete", methods=["POST"])
@role_required("admin")
def delete_announcement(announcement_id):
    execute("DELETE FROM announcements WHERE announcement_id = %s", (announcement_id,))
    flash("Announcement removed.", "info")
    return redirect(url_for("admin.announcements"))


# ---------------------------------------------------------------- audit log
@admin_bp.route("/audit-log")
@role_required("admin")
def audit_log():
    sql, params = "SELECT * FROM audit_log WHERE 1 = 1", []
    if request.args.get("operation"):
        sql += " AND operation = %s"
        params.append(request.args["operation"])
    if request.args.get("q"):
        sql += " AND details ILIKE %s"
        params.append(f"%{request.args['q'].strip()}%")
    rows = query_all(sql + " ORDER BY changed_at DESC, log_id DESC LIMIT 300", params)
    totals = query_all("SELECT operation, COUNT(*) AS n FROM audit_log GROUP BY operation")
    return render_template("admin/audit_log.html", rows=rows, totals={r["operation"]: r["n"] for r in totals}, filters=request.args)


# ---------------------------------------------------------------- database explorer
EXAMPLE_QUERIES = [
    ("Join: today's clinic", """SELECT a.appointment_time, p.full_name AS patient, d.full_name AS doctor, a.status
FROM appointments a
JOIN patients p ON p.patient_id = a.patient_id
JOIN doctors d ON d.doctor_id = a.doctor_id
WHERE a.appointment_date = CURRENT_DATE
ORDER BY a.appointment_time"""),
    ("Aggregate: visits per department", """SELECT dep.name AS department, COUNT(*) AS visits,
       ROUND(AVG(fn_patient_age(p.dob)), 1) AS avg_age
FROM appointments a
JOIN doctors d ON d.doctor_id = a.doctor_id
JOIN departments dep ON dep.department_id = d.department_id
JOIN patients p ON p.patient_id = a.patient_id
WHERE a.status = 'Completed'
GROUP BY dep.name
HAVING COUNT(*) > 50
ORDER BY visits DESC"""),
    ("Window function: rank doctors", """SELECT doctor_name, department, completed,
       RANK() OVER (ORDER BY completed DESC) AS overall_rank,
       RANK() OVER (PARTITION BY department ORDER BY completed DESC) AS rank_in_department
FROM view_doctor_performance
ORDER BY overall_rank"""),
    ("Correlated subquery: latest diagnosis", """SELECT p.full_name, mr.diagnosis, mr.created_at::date AS on_date
FROM patients p
JOIN medical_records mr ON mr.patient_id = p.patient_id
WHERE mr.created_at = (SELECT MAX(created_at) FROM medical_records WHERE patient_id = p.patient_id)
ORDER BY on_date DESC
LIMIT 20"""),
    ("CTE: monthly trend", """WITH monthly AS (
    SELECT date_trunc('month', appointment_date) AS month, status, COUNT(*) AS n
    FROM appointments GROUP BY 1, 2
)
SELECT to_char(month, 'Mon YYYY') AS month,
       SUM(n) FILTER (WHERE status = 'Completed') AS completed,
       SUM(n) FILTER (WHERE status = 'Cancelled') AS cancelled,
       SUM(n) FILTER (WHERE status = 'Scheduled') AS scheduled
FROM monthly GROUP BY month ORDER BY month"""),
    ("Set-returning function: free slots", """SELECT * FROM fn_free_slots(
    (SELECT doctor_id FROM doctors WHERE full_name = 'Dr. Anita Mehta'),
    CURRENT_DATE + 1)"""),
    ("Views: admin stats", "SELECT * FROM view_admin_stats"),
    ("Vitals: hypertensive readings", """SELECT p.full_name, mr.bp_systolic, mr.bp_diastolic, mr.created_at::date
FROM medical_records mr JOIN patients p ON p.patient_id = mr.patient_id
WHERE mr.bp_systolic >= 140 OR mr.bp_diastolic >= 90
ORDER BY mr.bp_systolic DESC
LIMIT 25"""),
    ("Catalog: table sizes", """SELECT relname AS table_name, n_live_tup AS approx_rows,
       pg_size_pretty(pg_total_relation_size(relid)) AS total_size
FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC"""),
]
BLOCKED = re.compile(r"\b(pg_terminate_backend|pg_cancel_backend|pg_reload_conf|pg_sleep|dblink\w*|lo_import|lo_export|pg_read_file|pg_read_binary_file|pg_ls_dir|set_config)\b", re.I)


def _catalog():
    tables = query_all(
        """SELECT c.relname AS name, pg_total_relation_size(c.oid) AS bytes, pg_size_pretty(pg_total_relation_size(c.oid)) AS size
           FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY c.relname"""
    )
    if tables:
        # Names come from the catalog, never from the request, so quoting them into SQL is safe.
        counts = query_all(" UNION ALL ".join(f"SELECT '{t['name']}' AS name, COUNT(*) AS n FROM \"{t['name']}\"" for t in tables))
        by_name = {r["name"]: r["n"] for r in counts}
        for t in tables:
            t["rows"] = by_name.get(t["name"], 0)
    return tables


def run_readonly(sql):
    """Run one SELECT-style statement in a READ ONLY transaction with a time limit. Returns (cols, rows, error, ms)."""
    statement = sql.strip().rstrip(";").strip()
    if not statement:
        return None, None, "Type a query first.", 0
    if ";" in statement:
        return None, None, "Run one statement at a time (remove the extra semicolons).", 0
    if statement.split(None, 1)[0].lower() not in ("select", "with", "explain", "table", "values", "show"):
        return None, None, "The console is read-only: start with SELECT, WITH, EXPLAIN, TABLE, VALUES or SHOW.", 0
    if BLOCKED.search(statement):
        return None, None, "That function is not allowed in the console.", 0
    conn = get_db()
    conn.rollback()  # start a fresh transaction so READ ONLY applies
    cur = conn.cursor()
    started = time.perf_counter()
    try:
        cur.execute("SET TRANSACTION READ ONLY")
        cur.execute("SET LOCAL statement_timeout = '5s'")
        cur.execute(statement)
        cols = [c[0] for c in cur.description] if cur.description else []
        rows = cur.fetchmany(200) if cols else []
        rows = [[f"<binary, {len(v)} bytes>" if isinstance(v, (bytes, bytearray, memoryview)) else v for v in r] for r in rows]
        return cols, rows, None, round((time.perf_counter() - started) * 1000, 1)
    except DatabaseError as e:
        return None, None, error_message(e), 0
    finally:
        cur.close()
        conn.rollback()


@admin_bp.route("/database", methods=["GET", "POST"])
@role_required("admin")
def database():
    tables = _catalog()
    names = [t["name"] for t in tables]
    selected = request.args.get("table") if request.args.get("table") in names else None
    browse = None
    if selected:
        columns = query_all(
            """SELECT column_name, data_type, is_nullable, column_default FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = %s ORDER BY ordinal_position""",
            (selected,),
        )
        keys = query_all(
            """SELECT tc.constraint_type, kcu.column_name, ccu.table_name AS ref_table, ccu.column_name AS ref_column
               FROM information_schema.table_constraints tc
               JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
               LEFT JOIN information_schema.constraint_column_usage ccu ON tc.constraint_type = 'FOREIGN KEY' AND ccu.constraint_name = tc.constraint_name
               WHERE tc.table_schema = 'public' AND tc.table_name = %s AND tc.constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY', 'UNIQUE')
               ORDER BY tc.constraint_type DESC, kcu.column_name""",
            (selected,),
        )
        cols, rows, _, _ = run_readonly(f'SELECT * FROM "{selected}" ORDER BY 1 DESC LIMIT 50')
        browse = {"columns": columns, "key_cols": keys, "cols": cols, "rows": rows}

    sql = request.form.get("sql", "") if request.method == "POST" else request.args.get("sql", "")
    result = None
    if sql:
        cols, rows, err, ms = run_readonly(sql)
        result = {"cols": cols, "rows": rows, "error": err, "ms": ms}

    objects = {
        "views": query_all("SELECT table_name FROM information_schema.views WHERE table_schema = 'public' ORDER BY table_name"),
        "routines": query_all(
            """SELECT p.proname AS name, CASE p.prokind WHEN 'p' THEN 'procedure' ELSE 'function' END AS kind,
                      pg_get_function_identity_arguments(p.oid) AS args
               FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
               WHERE n.nspname = 'public' AND p.prokind IN ('p', 'f') ORDER BY kind DESC, p.proname"""
        ),
        "triggers": query_all(
            """SELECT trigger_name, event_object_table, action_timing, string_agg(event_manipulation, ' OR ') AS events
               FROM information_schema.triggers WHERE trigger_schema = 'public'
               GROUP BY trigger_name, event_object_table, action_timing ORDER BY trigger_name"""
        ),
        "indexes": query_all("SELECT indexname, tablename, indexdef FROM pg_indexes WHERE schemaname = 'public' ORDER BY tablename, indexname"),
    }
    return render_template(
        "admin/database.html", tables=tables, selected=selected, browse=browse, sql=sql, result=result,
        examples=EXAMPLE_QUERIES, objects=objects, total_rows=sum(t["rows"] for t in tables),
    )
