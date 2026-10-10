from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session, url_for

from auth import role_required
from db import DatabaseError, error_message, execute, query_all, query_one

doctor_bp = Blueprint("doctor", __name__, url_prefix="/doctor")


def _did():
    return session["profile_id"]


@doctor_bp.route("/dashboard")
@role_required("doctor")
def dashboard():
    todays_appointments = query_all(
        """SELECT a.*, p.full_name AS patient_name, p.phone FROM appointments a
           JOIN patients p ON a.patient_id = p.patient_id
           WHERE a.doctor_id = %s AND a.appointment_date = CURRENT_DATE
           ORDER BY a.appointment_time""",
        (_did(),),
    )
    pending_tests = query_all(
        """SELECT lt.*, p.full_name AS patient_name FROM lab_tests lt
           JOIN patients p ON lt.patient_id = p.patient_id
           WHERE lt.doctor_id = %s AND lt.status = 'Pending'
           ORDER BY lt.requested_at DESC""",
        (_did(),),
    )
    return render_template(
        "doctor/dashboard.html", appointments=todays_appointments, pending_tests=pending_tests
    )


@doctor_bp.route("/appointments")
@role_required("doctor")
def appointments():
    all_appointments = query_all(
        """SELECT a.*, p.full_name AS patient_name, p.phone, p.patient_id FROM appointments a
           JOIN patients p ON a.patient_id = p.patient_id
           WHERE a.doctor_id = %s
           ORDER BY a.appointment_date DESC, a.appointment_time DESC""",
        (_did(),),
    )
    return render_template("doctor/appointments.html", appointments=all_appointments)


@doctor_bp.route("/appointments/<int:appointment_id>/complete", methods=["POST"])
@role_required("doctor")
def complete_appointment(appointment_id):
    execute(
        """UPDATE appointments SET status = 'Completed'
           WHERE appointment_id = %s AND doctor_id = %s""",
        (appointment_id, _did()),
    )
    flash("Appointment marked as completed.", "success")
    return redirect(url_for("doctor.appointments"))


@doctor_bp.route("/patients")
@role_required("doctor")
def patients():
    search = request.args.get("q", "").strip()
    if search:
        rows = query_all(
            "SELECT * FROM patients WHERE full_name ILIKE %s ORDER BY full_name",
            (f"%{search}%",),
        )
    else:
        rows = query_all(
            """SELECT DISTINCT p.* FROM patients p
               JOIN appointments a ON a.patient_id = p.patient_id
               WHERE a.doctor_id = %s ORDER BY p.full_name""",
            (_did(),),
        )
    return render_template("doctor/patients.html", patients=rows, search=search)


@doctor_bp.route("/patients/<int:patient_id>")
@role_required("doctor")
def patient_detail(patient_id):
    person = query_one("SELECT *, fn_patient_age(dob) AS age FROM patients WHERE patient_id = %s", (patient_id,))
    if person is None:
        abort(404)
    records = query_all(
        """SELECT mr.*, d.full_name AS doctor_name FROM medical_records mr
           JOIN doctors d ON mr.doctor_id = d.doctor_id
           WHERE mr.patient_id = %s ORDER BY mr.created_at DESC""",
        (patient_id,),
    )
    lab_tests = query_all(
        """SELECT lt.*, lr.result_summary, lr.uploaded_at FROM lab_tests lt
           LEFT JOIN lab_reports lr ON lr.lab_test_id = lt.lab_test_id
           WHERE lt.patient_id = %s ORDER BY lt.requested_at DESC""",
        (patient_id,),
    )
    appts = query_all(
        """SELECT * FROM appointments WHERE patient_id = %s
           ORDER BY appointment_date DESC, appointment_time DESC""",
        (patient_id,),
    )
    return render_template(
        "doctor/patient_detail.html",
        person=person,
        records=records,
        lab_tests=lab_tests,
        appointments=appts,
    )


@doctor_bp.route("/patients/<int:patient_id>/add-record", methods=["GET", "POST"])
@role_required("doctor")
def add_record(patient_id):
    person = query_one("SELECT * FROM patients WHERE patient_id = %s", (patient_id,))
    if person is None:
        abort(404)

    if request.method == "POST":
        diagnosis = request.form["diagnosis"].strip()
        prescription = request.form.get("prescription", "").strip()
        notes = request.form.get("notes", "").strip()
        appointment_id = request.form.get("appointment_id") or None

        try:
            if appointment_id:
                # Marks the visit Completed and saves the record in one transaction.
                execute(
                    "CALL sp_complete_visit(%s, %s, %s, %s, %s)",
                    (appointment_id, _did(), diagnosis, prescription, notes),
                )
            else:
                execute(
                    """INSERT INTO medical_records (patient_id, doctor_id, diagnosis, prescription, notes)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (patient_id, _did(), diagnosis, prescription, notes),
                )
            flash("Medical record added.", "success")
        except DatabaseError as e:
            flash(error_message(e), "danger")
        return redirect(url_for("doctor.patient_detail", patient_id=patient_id))

    open_appointments = query_all(
        """SELECT appointment_id, appointment_date, appointment_time FROM appointments
           WHERE patient_id = %s AND doctor_id = %s AND status = 'Scheduled'
           ORDER BY appointment_date""",
        (patient_id, _did()),
    )
    return render_template(
        "doctor/add_record.html", person=person, open_appointments=open_appointments
    )


@doctor_bp.route("/patients/<int:patient_id>/request-lab-test", methods=["GET", "POST"])
@role_required("doctor")
def request_lab_test(patient_id):
    person = query_one("SELECT * FROM patients WHERE patient_id = %s", (patient_id,))
    if person is None:
        abort(404)

    if request.method == "POST":
        test_name = request.form["test_name"].strip()
        execute(
            "INSERT INTO lab_tests (patient_id, doctor_id, test_name) VALUES (%s, %s, %s)",
            (patient_id, _did(), test_name),
        )
        flash("Lab test requested.", "success")
        return redirect(url_for("doctor.patient_detail", patient_id=patient_id))

    return render_template("doctor/request_lab_test.html", person=person)


@doctor_bp.route("/lab-reports/<int:report_id>/download")
@role_required("doctor")
def download_report(report_id):
    row = query_one(
        """SELECT lr.file_name, lr.file_type, lr.file_data FROM lab_reports lr
           JOIN lab_tests lt ON lr.lab_test_id = lt.lab_test_id
           WHERE lr.report_id = %s AND lt.doctor_id = %s""",
        (report_id, _did()),
    )
    if row is None or row["file_data"] is None:
        flash("No file attached to this report.", "warning")
        return redirect(url_for("doctor.dashboard"))

    return Response(
        bytes(row["file_data"]),
        mimetype=row["file_type"] or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={row['file_name']}"},
    )
