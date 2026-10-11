from datetime import date

from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, session, url_for

from auth import login_required, role_required
from db import DatabaseError, error_message, execute, query_all, query_one, today

patient_bp = Blueprint("patient", __name__, url_prefix="/patient")


def _pid():
    return session["profile_id"]


def vitals_series(patient_id, limit=12):
    """Chronological vitals for trend charts (oldest first)."""
    rows = query_all(
        """SELECT * FROM (
               SELECT created_at, bp_systolic, bp_diastolic, heart_rate, weight_kg, temperature_c
               FROM medical_records WHERE patient_id = %s AND bp_systolic IS NOT NULL
               ORDER BY created_at DESC LIMIT %s) v
           ORDER BY created_at""",
        (patient_id, limit),
    )
    return {
        "labels": [r["created_at"].strftime("%d %b") for r in rows],
        "systolic": [r["bp_systolic"] for r in rows],
        "diastolic": [r["bp_diastolic"] for r in rows],
        "heart_rate": [r["heart_rate"] for r in rows],
        "weight": [float(r["weight_kg"]) if r["weight_kg"] is not None else None for r in rows],
        "latest": rows[-1] if rows else None,
    }


def doctors_by_department():
    rows = query_all(
        """SELECT d.doctor_id, d.full_name, d.specialization, COALESCE(dep.name, 'Other') AS department
           FROM doctors d
           JOIN users u ON u.user_id = d.user_id AND u.is_active
           LEFT JOIN departments dep ON d.department_id = dep.department_id
           ORDER BY department, d.full_name"""
    )
    groups = {}
    for r in rows:
        groups.setdefault(r["department"], []).append(r)
    return groups


@patient_bp.route("/dashboard")
@role_required("patient")
def dashboard():
    next_appt = query_one(
        """SELECT a.*, d.full_name AS doctor_name, d.specialization, dep.name AS department
           FROM appointments a JOIN doctors d ON a.doctor_id = d.doctor_id
           LEFT JOIN departments dep ON d.department_id = dep.department_id
           WHERE a.patient_id = %s AND a.status = 'Scheduled' AND a.appointment_date >= CURRENT_DATE
           ORDER BY a.appointment_date, a.appointment_time LIMIT 1""",
        (_pid(),),
    )
    stats = query_one(
        """SELECT
               (SELECT COUNT(*) FROM appointments WHERE patient_id = %s AND status = 'Scheduled' AND appointment_date >= CURRENT_DATE) AS upcoming,
               (SELECT COUNT(*) FROM appointments WHERE patient_id = %s AND status = 'Completed') AS visits,
               (SELECT COUNT(*) FROM lab_tests WHERE patient_id = %s AND status = 'Pending') AS pending_tests,
               (SELECT COUNT(DISTINCT doctor_id) FROM appointments WHERE patient_id = %s) AS doctors""",
        (_pid(),) * 4,
    )
    recent_records = query_all(
        """SELECT mr.*, d.full_name AS doctor_name, dep.name AS department FROM medical_records mr
           JOIN doctors d ON mr.doctor_id = d.doctor_id LEFT JOIN departments dep ON d.department_id = dep.department_id
           WHERE mr.patient_id = %s ORDER BY mr.created_at DESC LIMIT 4""",
        (_pid(),),
    )
    upcoming = query_all(
        """SELECT a.*, d.full_name AS doctor_name, dep.name AS department FROM appointments a
           JOIN doctors d ON a.doctor_id = d.doctor_id LEFT JOIN departments dep ON d.department_id = dep.department_id
           WHERE a.patient_id = %s AND a.status = 'Scheduled' AND a.appointment_date >= CURRENT_DATE
           ORDER BY a.appointment_date, a.appointment_time LIMIT 5""",
        (_pid(),),
    )
    reports = query_all(
        """SELECT lt.test_name, lr.report_id, lr.result_summary, lr.uploaded_at, lr.file_name
           FROM lab_reports lr JOIN lab_tests lt ON lr.lab_test_id = lt.lab_test_id
           WHERE lt.patient_id = %s ORDER BY lr.uploaded_at DESC LIMIT 3""",
        (_pid(),),
    )
    return render_template(
        "patient/dashboard.html", next_appt=next_appt, stats=stats, recent_records=recent_records,
        upcoming=upcoming, reports=reports, vitals=vitals_series(_pid()), today=today(),
    )


@patient_bp.route("/profile", methods=["GET", "POST"])
@role_required("patient")
def profile():
    if request.method == "POST":
        execute(
            """UPDATE patients SET phone = %s, address = %s, emergency_contact = %s,
               blood_group = %s WHERE patient_id = %s""",
            (
                request.form.get("phone", ""),
                request.form.get("address", ""),
                request.form.get("emergency_contact", ""),
                request.form.get("blood_group", ""),
                _pid(),
            ),
        )
        flash("Profile updated.", "success")
        return redirect(url_for("patient.profile"))

    person = query_one(
        """SELECT p.*, fn_patient_age(p.dob) AS age, u.username, u.email, u.created_at AS member_since
           FROM patients p JOIN users u ON u.user_id = p.user_id WHERE p.patient_id = %s""",
        (_pid(),),
    )
    return render_template("patient/profile.html", person=person, vitals=vitals_series(_pid(), 1)["latest"])


@patient_bp.route("/appointments", methods=["GET", "POST"])
@role_required("patient")
def appointments():
    if request.method == "POST":
        doctor_id = request.form["doctor_id"]
        appointment_date = request.form["appointment_date"]
        appointment_time = request.form["appointment_time"]
        reason = request.form.get("reason", "")

        try:
            # Validation (past date, clinic hours, inactive doctor, slot clash) lives in the procedure.
            execute(
                "CALL sp_book_appointment(%s, %s, %s, %s, %s)",
                (_pid(), doctor_id, appointment_date, appointment_time, reason),
            )
            flash("Appointment booked.", "success")
        except DatabaseError as e:
            flash(error_message(e), "danger")
        return redirect(url_for("patient.appointments"))

    my_appointments = query_all(
        """SELECT a.*, d.full_name AS doctor_name, d.specialization, dep.name AS department,
                  (a.status = 'Scheduled' AND a.appointment_date >= CURRENT_DATE) AS is_upcoming
           FROM appointments a JOIN doctors d ON a.doctor_id = d.doctor_id
           LEFT JOIN departments dep ON d.department_id = dep.department_id
           WHERE a.patient_id = %s
           ORDER BY a.appointment_date DESC, a.appointment_time DESC""",
        (_pid(),),
    )
    return render_template(
        "patient/appointments.html", groups=doctors_by_department(), appointments=my_appointments,
        upcoming=[a for a in my_appointments if a["is_upcoming"]], history=[a for a in my_appointments if not a["is_upcoming"]],
        preselect=request.args.get("doctor_id", type=int),
    )


@patient_bp.route("/appointments/<int:appointment_id>/reschedule", methods=["POST"])
@role_required("patient")
def reschedule_appointment(appointment_id):
    try:
        # Cancels the old slot and books the new one in a single transaction.
        execute(
            "CALL sp_reschedule_appointment(%s, %s, %s, %s)",
            (appointment_id, _pid(), request.form["appointment_date"], request.form["appointment_time"]),
        )
        flash("Appointment rescheduled.", "success")
    except DatabaseError as e:
        flash(error_message(e), "danger")
    return redirect(url_for("patient.appointments"))


@patient_bp.route("/appointments/<int:appointment_id>/cancel", methods=["POST"])
@role_required("patient")
def cancel_appointment(appointment_id):
    execute(
        """UPDATE appointments SET status = 'Cancelled'
           WHERE appointment_id = %s AND patient_id = %s AND status = 'Scheduled'""",
        (appointment_id, _pid()),
    )
    flash("Appointment cancelled.", "info")
    return redirect(url_for("patient.appointments"))


@patient_bp.route("/api/slots")
@login_required
def slots():
    """Free/booked clinic slots for one doctor on one day, from fn_free_slots."""
    doctor_id = request.args.get("doctor_id", type=int)
    try:
        day = date.fromisoformat(request.args.get("date", ""))
    except ValueError:
        return jsonify({"slots": [], "closed": "Pick a valid date."})
    if doctor_id is None:
        return jsonify({"slots": [], "closed": "Pick a doctor."})
    if day < today():
        return jsonify({"slots": [], "closed": "That date is in the past."})
    if day.weekday() == 6:
        return jsonify({"slots": [], "closed": "The clinic is closed on Sundays."})
    rows = query_all("SELECT slot_time, is_free FROM fn_free_slots(%s, %s)", (doctor_id, day))
    return jsonify({"slots": [{"time": r["slot_time"].strftime("%H:%M"), "free": r["is_free"]} for r in rows], "closed": None})


@patient_bp.route("/records")
@role_required("patient")
def records():
    my_records = query_all(
        """SELECT mr.*, d.full_name AS doctor_name, d.specialization, dep.name AS department FROM medical_records mr
           JOIN doctors d ON mr.doctor_id = d.doctor_id LEFT JOIN departments dep ON d.department_id = dep.department_id
           WHERE mr.patient_id = %s ORDER BY mr.created_at DESC""",
        (_pid(),),
    )
    departments = sorted({r["department"] for r in my_records if r["department"]})
    return render_template("patient/records.html", records=my_records, departments=departments, vitals=vitals_series(_pid(), 20))


@patient_bp.route("/records/<int:record_id>/print")
@role_required("patient")
def print_record(record_id):
    record = query_one(
        """SELECT mr.*, d.full_name AS doctor_name, d.specialization, d.qualification, dep.name AS department,
                  p.full_name AS patient_name, p.dob, fn_patient_age(p.dob) AS age, p.gender, p.blood_group, p.phone,
                  a.appointment_date, a.appointment_time, a.reason
           FROM medical_records mr
           JOIN doctors d ON mr.doctor_id = d.doctor_id
           JOIN patients p ON mr.patient_id = p.patient_id
           LEFT JOIN departments dep ON d.department_id = dep.department_id
           LEFT JOIN appointments a ON a.appointment_id = mr.appointment_id
           WHERE mr.record_id = %s AND mr.patient_id = %s""",
        (record_id, _pid()),
    )
    if record is None:
        abort(404)
    return render_template("patient/record_print.html", r=record)


@patient_bp.route("/lab-reports")
@role_required("patient")
def lab_reports():
    tests = query_all(
        """SELECT lt.*, lr.report_id, lr.result_summary, lr.file_name, lr.uploaded_at,
                  doc.full_name AS requested_by
           FROM lab_tests lt
           JOIN doctors doc ON lt.doctor_id = doc.doctor_id
           LEFT JOIN lab_reports lr ON lr.lab_test_id = lt.lab_test_id
           WHERE lt.patient_id = %s ORDER BY lt.requested_at DESC""",
        (_pid(),),
    )
    return render_template("patient/lab_reports.html", tests=tests)


@patient_bp.route("/lab-reports/<int:report_id>/download")
@role_required("patient")
def download_report(report_id):
    row = query_one(
        """SELECT lr.file_name, lr.file_type, lr.file_data FROM lab_reports lr
           JOIN lab_tests lt ON lr.lab_test_id = lt.lab_test_id
           WHERE lr.report_id = %s AND lt.patient_id = %s""",
        (report_id, _pid()),
    )
    if row is None or row["file_data"] is None:
        flash("No file attached to this report.", "warning")
        return redirect(url_for("patient.lab_reports"))

    return Response(
        bytes(row["file_data"]),
        mimetype=row["file_type"] or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={row['file_name']}"},
    )
