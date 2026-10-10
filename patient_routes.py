from flask import Blueprint, Response, flash, redirect, render_template, request, session, url_for

from auth import role_required
from db import DatabaseError, error_message, execute, query_all, query_one

patient_bp = Blueprint("patient", __name__, url_prefix="/patient")


def _pid():
    return session["profile_id"]


@patient_bp.route("/dashboard")
@role_required("patient")
def dashboard():
    upcoming = query_all(
        """SELECT a.*, d.full_name AS doctor_name FROM appointments a
           JOIN doctors d ON a.doctor_id = d.doctor_id
           WHERE a.patient_id = %s AND a.status = 'Scheduled'
           ORDER BY a.appointment_date, a.appointment_time LIMIT 5""",
        (_pid(),),
    )
    recent_records = query_all(
        """SELECT mr.*, d.full_name AS doctor_name FROM medical_records mr
           JOIN doctors d ON mr.doctor_id = d.doctor_id
           WHERE mr.patient_id = %s ORDER BY mr.created_at DESC LIMIT 5""",
        (_pid(),),
    )
    pending_tests = query_one(
        "SELECT COUNT(*) AS n FROM lab_tests WHERE patient_id = %s AND status = 'Pending'",
        (_pid(),),
    )
    return render_template(
        "patient/dashboard.html",
        upcoming=upcoming,
        recent_records=recent_records,
        pending_tests=pending_tests["n"],
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

    person = query_one("SELECT * FROM patients WHERE patient_id = %s", (_pid(),))
    return render_template("patient/profile.html", person=person)


@patient_bp.route("/appointments", methods=["GET", "POST"])
@role_required("patient")
def appointments():
    if request.method == "POST":
        doctor_id = request.form["doctor_id"]
        appointment_date = request.form["appointment_date"]
        appointment_time = request.form["appointment_time"]
        reason = request.form.get("reason", "")

        try:
            # Validation (past date, inactive doctor, slot clash) lives in the procedure.
            execute(
                "CALL sp_book_appointment(%s, %s, %s, %s, %s)",
                (_pid(), doctor_id, appointment_date, appointment_time, reason),
            )
            flash("Appointment booked.", "success")
        except DatabaseError as e:
            flash(error_message(e), "danger")
        return redirect(url_for("patient.appointments"))

    doctors = query_all(
        """SELECT d.doctor_id, d.full_name, d.specialization, dep.name AS department
           FROM doctors d
           JOIN users u ON u.user_id = d.user_id AND u.is_active
           LEFT JOIN departments dep ON d.department_id = dep.department_id
           ORDER BY d.full_name"""
    )
    my_appointments = query_all(
        """SELECT a.*, d.full_name AS doctor_name, d.specialization FROM appointments a
           JOIN doctors d ON a.doctor_id = d.doctor_id
           WHERE a.patient_id = %s
           ORDER BY a.appointment_date DESC, a.appointment_time DESC""",
        (_pid(),),
    )
    return render_template(
        "patient/appointments.html", doctors=doctors, appointments=my_appointments
    )


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


@patient_bp.route("/records")
@role_required("patient")
def records():
    my_records = query_all(
        """SELECT mr.*, d.full_name AS doctor_name, d.specialization FROM medical_records mr
           JOIN doctors d ON mr.doctor_id = d.doctor_id
           WHERE mr.patient_id = %s ORDER BY mr.created_at DESC""",
        (_pid(),),
    )
    return render_template("patient/records.html", records=my_records)


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
