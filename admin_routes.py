from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from auth import role_required
from db import execute, query_all, query_one

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.route("/dashboard")
@role_required("admin")
def dashboard():
    stats = query_one("SELECT * FROM view_admin_stats")
    recent_appointments = query_all(
        """SELECT a.*, p.full_name AS patient_name, d.full_name AS doctor_name
           FROM appointments a
           JOIN patients p ON a.patient_id = p.patient_id
           JOIN doctors d ON a.doctor_id = d.doctor_id
           ORDER BY a.created_at DESC LIMIT 8"""
    )
    return render_template("admin/dashboard.html", stats=stats, recent=recent_appointments)


def _create_staff_account(username, email, password, role):
    existing = query_one(
        "SELECT user_id FROM users WHERE username = %s OR email = %s", (username, email)
    )
    if existing:
        return None
    user = execute(
        "INSERT INTO users (username, email, password_hash, role) VALUES (%s, %s, %s, %s) RETURNING user_id",
        (username, email, generate_password_hash(password), role),
    )
    return user["user_id"]


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
            flash("That username or email is already registered.", "danger")
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
                  fn_doctor_load(d.doctor_id, CURRENT_DATE) AS todays_load
           FROM doctors d
           JOIN users u ON d.user_id = u.user_id
           LEFT JOIN departments dep ON d.department_id = dep.department_id
           ORDER BY d.full_name"""
    )
    departments = query_all("SELECT * FROM departments ORDER BY name")
    return render_template("admin/doctors.html", doctors=rows, departments=departments)


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
            flash("That username or email is already registered.", "danger")
        else:
            execute(
                "INSERT INTO lab_assistants (user_id, full_name, phone) VALUES (%s, %s, %s)",
                (user_id, request.form["full_name"].strip(), request.form.get("phone", "")),
            )
            flash("Lab assistant account created.", "success")
        return redirect(url_for("admin.lab_assistants"))

    rows = query_all(
        """SELECT la.*, u.username, u.email, u.is_active FROM lab_assistants la
           JOIN users u ON la.user_id = u.user_id ORDER BY la.full_name"""
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
        """SELECT dep.*, COUNT(d.doctor_id) AS doctor_count FROM departments dep
           LEFT JOIN doctors d ON d.department_id = dep.department_id
           GROUP BY dep.department_id ORDER BY dep.name"""
    )
    return render_template("admin/departments.html", departments=rows)


@admin_bp.route("/departments/<int:department_id>/delete", methods=["POST"])
@role_required("admin")
def delete_department(department_id):
    # doctors.department_id is ON DELETE SET NULL, so doctors stay and just lose the department.
    execute("DELETE FROM departments WHERE department_id = %s", (department_id,))
    flash("Department deleted. Its doctors are now unassigned.", "info")
    return redirect(url_for("admin.departments"))


@admin_bp.route("/audit-log")
@role_required("admin")
def audit_log():
    rows = query_all("SELECT * FROM audit_log ORDER BY changed_at DESC, log_id DESC LIMIT 200")
    return render_template("admin/audit_log.html", rows=rows)


@admin_bp.route("/patients")
@role_required("admin")
def patients():
    search = request.args.get("q", "").strip()
    if search:
        rows = query_all(
            """SELECT p.*, fn_patient_age(p.dob) AS age, u.username, u.email, u.is_active FROM patients p
               JOIN users u ON p.user_id = u.user_id
               WHERE p.full_name ILIKE %s ORDER BY p.full_name""",
            (f"%{search}%",),
        )
    else:
        rows = query_all(
            """SELECT p.*, fn_patient_age(p.dob) AS age, u.username, u.email, u.is_active FROM patients p
               JOIN users u ON p.user_id = u.user_id ORDER BY p.full_name"""
        )
    return render_template("admin/patients.html", patients=rows, search=search)


@admin_bp.route("/patients/<int:patient_id>")
@role_required("admin")
def patient_detail(patient_id):
    person = query_one(
        """SELECT p.*, u.username, u.email FROM patients p
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
        "admin/patient_detail.html", person=person, records=records, appointments=appts
    )


@admin_bp.route("/appointments")
@role_required("admin")
def appointments():
    rows = query_all(
        """SELECT a.*, p.full_name AS patient_name, d.full_name AS doctor_name
           FROM appointments a
           JOIN patients p ON a.patient_id = p.patient_id
           JOIN doctors d ON a.doctor_id = d.doctor_id
           ORDER BY a.appointment_date DESC, a.appointment_time DESC"""
    )
    return render_template("admin/appointments.html", appointments=rows)
