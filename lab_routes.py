from flask import Blueprint, Response, abort, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

from auth import role_required
from db import execute, query_all, query_one

lab_bp = Blueprint("lab", __name__, url_prefix="/lab")


def _lid():
    return session["profile_id"]


def _allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]
    )


@lab_bp.route("/dashboard")
@role_required("lab_assistant")
def dashboard():
    stats = query_one(
        """SELECT
               (SELECT COUNT(*) FROM lab_tests WHERE status = 'Pending') AS pending,
               (SELECT COUNT(*) FROM lab_tests WHERE status = 'Pending' AND requested_at < LOCALTIMESTAMP - INTERVAL '3 days') AS overdue,
               (SELECT COUNT(*) FROM lab_reports WHERE lab_assistant_id = %s) AS mine,
               (SELECT ROUND(AVG(EXTRACT(EPOCH FROM lr.uploaded_at - lt.requested_at) / 3600)::numeric, 1)
                  FROM lab_reports lr JOIN lab_tests lt ON lt.lab_test_id = lr.lab_test_id
                  WHERE lr.uploaded_at > LOCALTIMESTAMP - INTERVAL '30 days') AS avg_hours""",
        (_lid(),),
    )
    daily = query_all(
        """SELECT to_char(day, 'DD Mon') AS label,
                  COUNT(lr.report_id) FILTER (WHERE lr.lab_assistant_id = %s) AS mine,
                  COUNT(lr.report_id) AS team
           FROM generate_series(CURRENT_DATE - 13, CURRENT_DATE, INTERVAL '1 day') AS day
           LEFT JOIN lab_reports lr ON lr.uploaded_at::date = day::date
           GROUP BY day ORDER BY day""",
        (_lid(),),
    )
    by_type = query_all("SELECT test_name, COUNT(*) AS n FROM lab_tests GROUP BY test_name ORDER BY n DESC LIMIT 8")
    queue = query_all(
        """SELECT lt.lab_test_id, lt.test_name, lt.requested_at, p.full_name AS patient_name,
                  (CURRENT_DATE - lt.requested_at::date) AS days
           FROM lab_tests lt JOIN patients p ON lt.patient_id = p.patient_id
           WHERE lt.status = 'Pending' ORDER BY lt.requested_at LIMIT 6"""
    )
    recent_uploads = query_all(
        """SELECT lr.report_id, lr.uploaded_at, lt.test_name, p.full_name AS patient_name FROM lab_reports lr
           JOIN lab_tests lt ON lr.lab_test_id = lt.lab_test_id
           JOIN patients p ON lt.patient_id = p.patient_id
           WHERE lr.lab_assistant_id = %s ORDER BY lr.uploaded_at DESC LIMIT 5""",
        (_lid(),),
    )
    return render_template(
        "lab/dashboard.html", stats=stats, queue=queue, recent_uploads=recent_uploads,
        daily={"labels": [r["label"] for r in daily], "mine": [r["mine"] for r in daily], "team": [r["team"] for r in daily]},
        by_type={"labels": [r["test_name"] for r in by_type], "values": [r["n"] for r in by_type]},
    )


@lab_bp.route("/pending-tests")
@role_required("lab_assistant")
def pending_tests():
    tests = query_all(
        """SELECT lt.*, p.full_name AS patient_name, fn_patient_age(p.dob) AS age, doc.full_name AS requested_by,
                  (CURRENT_DATE - lt.requested_at::date) AS days
           FROM lab_tests lt
           JOIN patients p ON lt.patient_id = p.patient_id
           JOIN doctors doc ON lt.doctor_id = doc.doctor_id
           WHERE lt.status = 'Pending' ORDER BY lt.requested_at ASC"""
    )
    return render_template("lab/pending_tests.html", tests=tests, test_types=sorted({t["test_name"] for t in tests}))


@lab_bp.route("/upload/<int:lab_test_id>", methods=["GET", "POST"])
@role_required("lab_assistant")
def upload_report(lab_test_id):
    test = query_one(
        """SELECT lt.*, p.full_name AS patient_name FROM lab_tests lt
           JOIN patients p ON lt.patient_id = p.patient_id
           WHERE lt.lab_test_id = %s""",
        (lab_test_id,),
    )
    if test is None:
        abort(404)
    if test["status"] == "Completed":
        flash("A report has already been uploaded for this test.", "warning")
        return redirect(url_for("lab.pending_tests"))

    if request.method == "POST":
        result_summary = request.form["result_summary"].strip()
        file = request.files.get("report_file")

        file_name = file_type = file_bytes = None
        if file and file.filename:
            if not _allowed_file(file.filename):
                flash("Only PDF, PNG, or JPG files are allowed.", "danger")
                return render_template("lab/upload_report.html", test=test)
            file_name = secure_filename(file.filename)
            file_type = file.mimetype
            file_bytes = file.read()

        execute(
            """INSERT INTO lab_reports
               (lab_test_id, lab_assistant_id, result_summary, file_name, file_type, file_data)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                lab_test_id,
                _lid(),
                result_summary,
                file_name,
                file_type,
                file_bytes,
            ),
        )
        flash("Lab report uploaded successfully.", "success")
        return redirect(url_for("lab.pending_tests"))

    return render_template("lab/upload_report.html", test=test)


@lab_bp.route("/reports")
@role_required("lab_assistant")
def report_history():
    reports = query_all(
        """SELECT lr.report_id, lr.result_summary, lr.file_name, lr.uploaded_at, lt.test_name, p.full_name AS patient_name,
                  ROUND(EXTRACT(EPOCH FROM lr.uploaded_at - lt.requested_at) / 3600) AS hours
           FROM lab_reports lr
           JOIN lab_tests lt ON lr.lab_test_id = lt.lab_test_id
           JOIN patients p ON lt.patient_id = p.patient_id
           WHERE lr.lab_assistant_id = %s ORDER BY lr.uploaded_at DESC""",
        (_lid(),),
    )
    return render_template("lab/report_history.html", reports=reports)


@lab_bp.route("/reports/<int:report_id>/download")
@role_required("lab_assistant")
def download_report(report_id):
    row = query_one(
        "SELECT file_name, file_type, file_data FROM lab_reports WHERE report_id = %s AND lab_assistant_id = %s",
        (report_id, _lid()),
    )
    if row is None or row["file_data"] is None:
        flash("No file attached to this report.", "warning")
        return redirect(url_for("lab.report_history"))

    return Response(
        bytes(row["file_data"]),
        mimetype=row["file_type"] or "application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={row['file_name']}"},
    )
