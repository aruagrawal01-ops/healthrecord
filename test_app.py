"""End-to-end checks: CRUD for every role plus edge cases, through the real Flask app.

WRITES DATA. Point DATABASE_URL at a disposable database loaded with
schema.sql, advanced_features.sql, seed_data.sql and bulk_demo_data.sql, then:
    python3 test_app.py
"""
import io
from datetime import date, timedelta

from app import app
from db import query_one

FUTURE = (date.today() + timedelta(days=40)).isoformat()
PAST = (date.today() - timedelta(days=1)).isoformat()
results = []


def check(name, condition):
    results.append((name, bool(condition)))
    print(("PASS  " if condition else "FAIL  ") + name)


def one(sql, params=()):
    with app.app_context():
        return query_one(sql, params)


def login(username, password, role):
    c = app.test_client()
    r = c.post("/login", data={"username": username, "password": password, "role": role}, follow_redirects=True)
    return c, r


# ---- Authentication and role-based access ----
patient, r = login("rahul", "patient123", "patient")
check("Patient login reaches dashboard", b"Welcome, Rahul Sharma" in r.data)
doctor, r = login("drmehta", "doctor123", "doctor")
check("Doctor login reaches dashboard", b"Today's Appointments" in r.data)
lab, r = login("labtech", "lab123", "lab_assistant")
check("Lab assistant login reaches dashboard", b"Pending Tests" in r.data)
admin, r = login("admin", "admin123", "admin")
check("Admin login reaches dashboard", b"Hospital Overview" in r.data)
_, r = login("rahul", "wrong-password", "patient")
check("Edge: wrong password is rejected", b"Invalid username, password, or role" in r.data)
_, r = login("rahul", "patient123", "doctor")
check("Edge: right password, wrong role is rejected", b"Invalid username, password, or role" in r.data)
r = patient.get("/admin/dashboard", follow_redirects=True)
check("Edge: patient cannot open admin pages", b"You do not have access" in r.data)
r = app.test_client().get("/patient/records", follow_redirects=True)
check("Edge: logged-out user is sent to login", b"Please log in" in r.data)

for c, pages in [(patient, ["/patient/dashboard", "/patient/appointments", "/patient/records", "/patient/lab-reports", "/patient/profile"]),
                 (doctor, ["/doctor/dashboard", "/doctor/appointments", "/doctor/patients", "/doctor/patients/1"]),
                 (lab, ["/lab/dashboard", "/lab/pending-tests", "/lab/reports"]),
                 (admin, ["/admin/dashboard", "/admin/doctors", "/admin/lab-assistants", "/admin/patients",
                          "/admin/departments", "/admin/appointments", "/admin/audit-log", "/admin/patients/1"])]:
    check(f"Read: {len(pages)} pages load ({pages[0].split('/')[1]})", all(c.get(p).status_code == 200 for p in pages))

# ---- Patient: register (create), book (create), clash/past (edge), cancel and profile (update) ----
r = app.test_client().post("/register", data={"username": "testuser1", "email": "t1@example.com", "password": "secret1",
                                              "full_name": "Test User", "dob": "2000-01-01", "gender": "Other"}, follow_redirects=True)
check("Create: patient self-registration", b"Registration successful" in r.data)
r = app.test_client().post("/register", data={"username": "testuser1", "email": "t2@example.com", "password": "secret1",
                                              "full_name": "Dup", "dob": "2000-01-01", "gender": "Other"}, follow_redirects=True)
check("Edge: duplicate username is rejected", b"already registered" in r.data)
r = app.test_client().post("/register", data={"username": "shortpw", "email": "s@example.com", "password": "123",
                                              "full_name": "Short", "dob": "2000-01-01", "gender": "Other"}, follow_redirects=True)
check("Edge: password under 6 characters is rejected", b"at least 6 characters" in r.data)

booking = {"doctor_id": "1", "appointment_date": FUTURE, "appointment_time": "16:00", "reason": "Test booking"}
r = patient.post("/patient/appointments", data=booking, follow_redirects=True)
check("Create: patient books an appointment (sp_book_appointment)", b"Appointment booked" in r.data)
priya, _ = login("priya", "patient123", "patient")
r = priya.post("/patient/appointments", data=booking, follow_redirects=True)
check("Edge: appointment clash is blocked", b"already booked" in r.data)
r = patient.post("/patient/appointments", data=dict(booking, appointment_date=PAST, appointment_time="09:05"), follow_redirects=True)
check("Edge: booking in the past is blocked", b"cannot be in the past" in r.data)

appt = one("SELECT appointment_id FROM appointments WHERE appointment_date = %s AND appointment_time = '16:00' AND doctor_id = 1", (FUTURE,))
patient.post(f"/patient/appointments/{appt['appointment_id']}/cancel")
check("Update: patient cancels appointment", one("SELECT status FROM appointments WHERE appointment_id = %s", (appt["appointment_id"],))["status"] == "Cancelled")
r = priya.post("/patient/appointments", data=booking, follow_redirects=True)
check("Edge: a cancelled slot can be booked again", b"Appointment booked" in r.data)
patient.post("/patient/profile", data={"phone": "9000000001", "address": "Updated address", "emergency_contact": "9000000002", "blood_group": "O+"})
check("Update: patient edits profile", one("SELECT phone FROM patients WHERE full_name = 'Rahul Sharma'")["phone"] == "9000000001")

# ---- Doctor: complete visit via procedure (update + create + audit trigger), request lab test (create) ----
visit = one("""SELECT a.appointment_id, a.patient_id FROM appointments a
               WHERE a.doctor_id = 1 AND a.status = 'Scheduled' AND a.appointment_date = CURRENT_DATE ORDER BY a.appointment_id LIMIT 1""")
logs_before = one("SELECT COUNT(*) AS n FROM audit_log")["n"]
doctor.post(f"/doctor/patients/{visit['patient_id']}/add-record",
            data={"appointment_id": visit["appointment_id"], "diagnosis": "Test diagnosis", "prescription": "Test Rx", "notes": ""})
check("Update+Create: sp_complete_visit completes appointment and saves record",
      one("SELECT status FROM appointments WHERE appointment_id = %s", (visit["appointment_id"],))["status"] == "Completed"
      and one("SELECT COUNT(*) AS n FROM medical_records WHERE appointment_id = %s", (visit["appointment_id"],))["n"] == 1)
check("Trigger: trg_medical_record_audit logged the new record", one("SELECT COUNT(*) AS n FROM audit_log")["n"] == logs_before + 1)
doctor.post(f"/doctor/patients/{visit['patient_id']}/request-lab-test", data={"test_name": "Test HbA1c"})
test = one("SELECT lab_test_id, status FROM lab_tests WHERE test_name = 'Test HbA1c'")
check("Create: doctor requests a lab test (Pending)", test and test["status"] == "Pending")

# ---- Lab assistant: invalid file (edge), upload (create + trigger), download (read) ----
r = lab.post(f"/lab/upload/{test['lab_test_id']}", data={"result_summary": "x", "report_file": (io.BytesIO(b"MZ"), "virus.exe")},
             content_type="multipart/form-data", follow_redirects=True)
check("Edge: non-PDF/image upload is rejected", b"Only PDF, PNG, or JPG" in r.data)
pdf = b"%PDF-1.4 test report"
lab.post(f"/lab/upload/{test['lab_test_id']}", data={"result_summary": "HbA1c 5.4%", "report_file": (io.BytesIO(pdf), "hba1c.pdf")},
         content_type="multipart/form-data")
check("Trigger: trg_lab_report_insert marked the test Completed",
      one("SELECT status FROM lab_tests WHERE lab_test_id = %s", (test["lab_test_id"],))["status"] == "Completed")
report = one("SELECT report_id FROM lab_reports WHERE lab_test_id = %s", (test["lab_test_id"],))
check("Read: uploaded file downloads byte-for-byte", lab.get(f"/lab/reports/{report['report_id']}/download").data == pdf)

# ---- Admin: department create/delete (FK SET NULL), doctor create, toggle (update) ----
admin.post("/admin/departments", data={"name": "Test Dept"})
dept = one("SELECT department_id FROM departments WHERE name = 'Test Dept'")
check("Create: admin adds a department", dept is not None)
admin.post("/admin/doctors", data={"full_name": "Dr. Test Doc", "username": "drtestdoc", "email": "td@hospital.com", "password": "secret1",
                                   "specialization": "Test", "qualification": "MBBS", "department_id": dept["department_id"], "phone": ""})
doc = one("SELECT doctor_id, department_id FROM doctors WHERE full_name = 'Dr. Test Doc'")
check("Create: admin adds a doctor account", doc and doc["department_id"] == dept["department_id"])
admin.post(f"/admin/doctors/{doc['doctor_id']}/toggle")
check("Update: admin deactivates the doctor",
      one("SELECT u.is_active FROM users u JOIN doctors d ON d.user_id = u.user_id WHERE d.doctor_id = %s", (doc["doctor_id"],))["is_active"] is False)
_, r = login("drtestdoc", "secret1", "doctor")
check("Edge: deactivated account cannot log in", b"Invalid username, password, or role" in r.data)
r = patient.post("/patient/appointments", data=dict(booking, doctor_id=doc["doctor_id"], appointment_time="10:10"), follow_redirects=True)
check("Edge: cannot book an inactive doctor", b"not available" in r.data)
admin.post(f"/admin/departments/{dept['department_id']}/delete")
check("Delete: admin deletes department; doctor kept with department NULL (ON DELETE SET NULL)",
      one("SELECT department_id FROM departments WHERE name = 'Test Dept'") is None
      and one("SELECT department_id FROM doctors WHERE doctor_id = %s", (doc["doctor_id"],))["department_id"] is None)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
raise SystemExit(1 if failed else 0)
