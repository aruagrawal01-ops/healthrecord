from datetime import date, timedelta

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session, url_for

from auth import role_required
from db import DatabaseError, error_message, execute, query_all, query_one, today
from patient_routes import vitals_series

doctor_bp = Blueprint("doctor", __name__, url_prefix="/doctor")

CLINIC_SLOTS = [f"{h:02d}:{m:02d}" for h in (9, 10, 11, 12, 14, 15, 16) for m in (0, 30)]
COMMON_TESTS = ["Complete Blood Count", "Lipid Profile", "HbA1c", "Fasting Blood Sugar", "Thyroid Profile (TSH)", "Vitamin D (25-OH)",
                "Vitamin B12", "ECG", "2D Echo", "Chest X-Ray", "MRI Brain", "Urine Culture", "Serum IgE", "Hemoglobin"]


def _did():
    return session["profile_id"]


@doctor_bp.route("/dashboard")
@role_required("doctor")
def dashboard():
    todays_appointments = query_all(
        """SELECT a.*, p.full_name AS patient_name, p.phone, fn_patient_age(p.dob) AS age, p.gender FROM appointments a
           JOIN patients p ON a.patient_id = p.patient_id
           WHERE a.doctor_id = %s AND a.appointment_date = CURRENT_DATE
           ORDER BY a.appointment_time""",
        (_did(),),
    )
    stats = query_one(
        """SELECT
               (SELECT COUNT(*) FROM appointments WHERE doctor_id = %s AND appointment_date BETWEEN CURRENT_DATE AND CURRENT_DATE + 6 AND status = 'Scheduled') AS week,
               (SELECT COUNT(DISTINCT patient_id) FROM appointments WHERE doctor_id = %s) AS patients,
               (SELECT COUNT(*) FROM appointments WHERE doctor_id = %s AND status = 'Completed') AS completed,
               (SELECT COUNT(*) FROM lab_tests WHERE doctor_id = %s AND status = 'Pending') AS pending_labs""",
        (_did(),) * 4,
    )
    trend = query_all(
        """SELECT to_char(week, 'DD Mon') AS label,
                  COUNT(a.appointment_id) FILTER (WHERE a.status = 'Completed') AS completed,
                  COUNT(a.appointment_id) FILTER (WHERE a.status = 'Cancelled') AS cancelled
           FROM generate_series(date_trunc('week', CURRENT_DATE) - INTERVAL '11 weeks', date_trunc('week', CURRENT_DATE), INTERVAL '1 week') AS week
           LEFT JOIN appointments a ON a.doctor_id = %s AND a.appointment_date >= week AND a.appointment_date < week + INTERVAL '7 days'
           GROUP BY week ORDER BY week""",
        (_did(),),
    )
    reasons = query_all(
        """SELECT reason, COUNT(*) AS n FROM appointments WHERE doctor_id = %s AND reason IS NOT NULL
           GROUP BY reason ORDER BY n DESC LIMIT 6""",
        (_did(),),
    )
    pending_tests = query_all(
        """SELECT lt.*, p.full_name AS patient_name, (CURRENT_DATE - lt.requested_at::date) AS days FROM lab_tests lt
           JOIN patients p ON lt.patient_id = p.patient_id
           WHERE lt.doctor_id = %s AND lt.status = 'Pending'
           ORDER BY lt.requested_at LIMIT 8""",
        (_did(),),
    )
    return render_template(
        "doctor/dashboard.html", appointments=todays_appointments, stats=stats, pending_tests=pending_tests, today=today(),
        trend={"labels": [r["label"] for r in trend], "completed": [r["completed"] for r in trend], "cancelled": [r["cancelled"] for r in trend]},
        reasons={"labels": [r["reason"] for r in reasons], "values": [r["n"] for r in reasons]},
    )


@doctor_bp.route("/schedule")
@role_required("doctor")
def schedule():
    try:
        start = date.fromisoformat(request.args.get("start", ""))
    except ValueError:
        start = today() + timedelta(days=1 if today().weekday() == 6 else 0)  # on Sundays show the coming week
    start -= timedelta(days=start.weekday())  # Monday of that week
    days = [start + timedelta(days=i) for i in range(6)]  # Monday to Saturday
    rows = query_all(
        """SELECT a.appointment_id, a.appointment_date, a.appointment_time, a.status, a.reason, p.patient_id, p.full_name AS patient_name
           FROM appointments a JOIN patients p ON a.patient_id = p.patient_id
           WHERE a.doctor_id = %s AND a.appointment_date BETWEEN %s AND %s
           ORDER BY a.status = 'Cancelled'""",
        (_did(), days[0], days[-1]),
    )
    grid = {}
    for r in rows:
        grid.setdefault((r["appointment_date"], r["appointment_time"].strftime("%H:%M")), []).append(r)
    counts = {d: sum(1 for r in rows if r["appointment_date"] == d and r["status"] != "Cancelled") for d in days}
    return render_template("doctor/schedule.html", days=days, slots=CLINIC_SLOTS, grid=grid, counts=counts, today=today(),
                           prev=days[0] - timedelta(days=7), next=days[0] + timedelta(days=7), total=sum(counts.values()))


@doctor_bp.route("/appointments")
@role_required("doctor")
def appointments():
    status = request.args.get("status", "")
    when = request.args.get("when", "upcoming")
    q = request.args.get("q", "").strip()
    sql = """SELECT a.*, p.full_name AS patient_name, p.phone, p.patient_id FROM appointments a
             JOIN patients p ON a.patient_id = p.patient_id WHERE a.doctor_id = %s"""
    params = [_did()]
    if status:
        sql += " AND a.status = %s"
        params.append(status)
    if when == "upcoming":
        sql += " AND a.appointment_date >= CURRENT_DATE"
    elif when == "past":
        sql += " AND a.appointment_date < CURRENT_DATE"
    if q:
        sql += " AND p.full_name ILIKE %s"
        params.append(f"%{q}%")
    sql += " ORDER BY a.appointment_date " + ("ASC" if when == "upcoming" else "DESC") + ", a.appointment_time LIMIT 300"
    return render_template("doctor/appointments.html", appointments=query_all(sql, params), status=status, when=when, q=q)


@doctor_bp.route("/appointments/<int:appointment_id>/complete", methods=["POST"])
@role_required("doctor")
def complete_appointment(appointment_id):
    execute(
        """UPDATE appointments SET status = 'Completed'
           WHERE appointment_id = %s AND doctor_id = %s""",
        (appointment_id, _did()),
    )
    flash("Appointment marked as completed.", "success")
    back = request.form.get("back")
    return redirect(url_for(back if back in ("doctor.dashboard", "doctor.schedule") else "doctor.appointments"))


@doctor_bp.route("/patients")
@role_required("doctor")
def patients():
    search = request.args.get("q", "").strip()
    base = """SELECT p.*, fn_patient_age(p.dob) AS age,
                     COUNT(a.appointment_id) FILTER (WHERE a.doctor_id = %s) AS visits_with_me,
                     MAX(a.appointment_date) FILTER (WHERE a.doctor_id = %s AND a.appointment_date <= CURRENT_DATE) AS last_visit
              FROM patients p LEFT JOIN appointments a ON a.patient_id = p.patient_id"""
    if search:
        rows = query_all(base + " WHERE p.full_name ILIKE %s GROUP BY p.patient_id ORDER BY p.full_name", (_did(), _did(), f"%{search}%"))
    else:
        rows = query_all(
            base + " GROUP BY p.patient_id HAVING COUNT(a.appointment_id) FILTER (WHERE a.doctor_id = %s) > 0 ORDER BY last_visit DESC NULLS LAST",
            (_did(), _did(), _did()),
        )
    return render_template("doctor/patients.html", patients=rows, search=search)


@doctor_bp.route("/patients/<int:patient_id>")
@role_required("doctor")
def patient_detail(patient_id):
    person = query_one("SELECT *, fn_patient_age(dob) AS age FROM patients WHERE patient_id = %s", (patient_id,))
    if person is None:
        abort(404)
    records = query_all(
        """SELECT mr.*, d.full_name AS doctor_name, dep.name AS department FROM medical_records mr
           JOIN doctors d ON mr.doctor_id = d.doctor_id LEFT JOIN departments dep ON d.department_id = dep.department_id
           WHERE mr.patient_id = %s ORDER BY mr.created_at DESC""",
        (patient_id,),
    )
    lab_tests = query_all(
        """SELECT lt.*, lr.report_id, lr.result_summary, lr.uploaded_at, lr.file_name FROM lab_tests lt
           LEFT JOIN lab_reports lr ON lr.lab_test_id = lt.lab_test_id
           WHERE lt.patient_id = %s ORDER BY lt.requested_at DESC""",
        (patient_id,),
    )
    appts = query_all(
        """SELECT a.*, d.full_name AS doctor_name FROM appointments a JOIN doctors d ON d.doctor_id = a.doctor_id
           WHERE a.patient_id = %s ORDER BY a.appointment_date DESC, a.appointment_time DESC""",
        (patient_id,),
    )
    return render_template(
        "doctor/patient_detail.html", person=person, records=records, lab_tests=lab_tests,
        appointments=appts, vitals=vitals_series(patient_id, 15),
    )


def _num(name):
    """Optional numeric form field: blank becomes NULL, the database CHECKs enforce ranges."""
    value = request.form.get(name, "").strip()
    return value or None


@doctor_bp.route("/patients/<int:patient_id>/add-record", methods=["GET", "POST"])
@role_required("doctor")
def add_record(patient_id):
    person = query_one("SELECT *, fn_patient_age(dob) AS age FROM patients WHERE patient_id = %s", (patient_id,))
    if person is None:
        abort(404)

    if request.method == "POST":
        diagnosis = request.form["diagnosis"].strip()
        prescription = request.form.get("prescription", "").strip()
        notes = request.form.get("notes", "").strip()
        appointment_id = request.form.get("appointment_id") or None
        vitals = [_num(f) for f in ("bp_systolic", "bp_diastolic", "heart_rate", "temperature_c", "weight_kg")]

        try:
            if appointment_id:
                # Marks the visit Completed and saves the record (with vitals) in one transaction.
                execute(
                    "CALL sp_complete_visit(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (appointment_id, _did(), diagnosis, prescription, notes, *vitals),
                )
            else:
                execute(
                    """INSERT INTO medical_records (patient_id, doctor_id, diagnosis, prescription, notes,
                                                    bp_systolic, bp_diastolic, heart_rate, temperature_c, weight_kg)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (patient_id, _did(), diagnosis, prescription, notes, *vitals),
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
        "doctor/add_record.html", person=person, open_appointments=open_appointments,
        preselect=request.args.get("appointment_id", type=int), last=vitals_series(patient_id, 1)["latest"],
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

    return render_template("doctor/request_lab_test.html", person=person, tests=COMMON_TESTS)


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
