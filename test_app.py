"""End-to-end checks: CRUD for every role plus edge cases, through the real Flask app.

WRITES DATA. Point DATABASE_URL at a disposable database loaded with
schema.sql, advanced_features.sql, seed_data.sql and bulk_demo_data.sql, then:
    python3 test_app.py
"""
import io
from datetime import date, timedelta

from app import app
from db import query_one, today


def weekday(offset):
    """A clinic day (Mon-Sat) at least `offset` days from today."""
    d = today() + timedelta(days=offset)
    return (d + timedelta(days=1) if d.weekday() == 6 else d).isoformat()


FUTURE = weekday(40)
LATER = weekday(45)
PAST = (today() - timedelta(days=1)).isoformat()
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

for c, pages in [(patient, ["/patient/dashboard", "/patient/appointments", "/patient/records", "/patient/lab-reports", "/patient/profile",
                            "/account/password"]),
                 (doctor, ["/doctor/dashboard", "/doctor/appointments", "/doctor/appointments?when=past", "/doctor/schedule",
                           "/doctor/patients", "/doctor/patients?q=a", "/doctor/patients/1", "/doctor/patients/1/add-record"]),
                 (lab, ["/lab/dashboard", "/lab/pending-tests", "/lab/reports"]),
                 (admin, ["/admin/dashboard", "/admin/reports", "/admin/doctors", "/admin/lab-assistants", "/admin/patients",
                          "/admin/patients?gender=Female&blood_group=O%2B", "/admin/departments", "/admin/appointments",
                          "/admin/appointments?status=Completed&department=2", "/admin/announcements", "/admin/audit-log",
                          "/admin/audit-log?operation=INSERT&q=hyper", "/admin/patients/1", "/admin/database", "/admin/database?table=appointments"])]:
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

slots = patient.get(f"/patient/api/slots?doctor_id=1&date={FUTURE}").get_json()
check("Read: slot API lists 14 clinic slots", len(slots["slots"]) == 14 and slots["closed"] is None)
booking = {"doctor_id": "1", "appointment_date": FUTURE, "appointment_time": "16:00", "reason": "Test booking"}
r = patient.post("/patient/appointments", data=booking, follow_redirects=True)
check("Create: patient books an appointment (sp_book_appointment)", b"Appointment booked" in r.data)
priya, _ = login("priya", "patient123", "patient")
r = priya.post("/patient/appointments", data=booking, follow_redirects=True)
check("Edge: appointment clash is blocked", b"already booked" in r.data)
r = patient.post("/patient/appointments", data=dict(booking, appointment_date=PAST, appointment_time="09:05"), follow_redirects=True)
check("Edge: booking in the past is blocked", b"cannot be in the past" in r.data)
taken = patient.get(f"/patient/api/slots?doctor_id=1&date={FUTURE}").get_json()
check("Read: slot API shows the booked slot as taken", any(s["time"] == "16:00" and not s["free"] for s in taken["slots"]))
r = patient.post("/patient/appointments", data=dict(booking, appointment_time="13:00"), follow_redirects=True)
check("Edge: lunch-hour slot is rejected", b"choose a clinic slot" in r.data)
sunday = (today() + timedelta(days=(6 - today().weekday()) % 7 or 7)).isoformat()
r = patient.post("/patient/appointments", data=dict(booking, appointment_date=sunday), follow_redirects=True)
check("Edge: Sunday booking is rejected", b"closed on Sundays" in r.data)
check("Read: slot API reports Sundays closed", "Sunday" in (patient.get(f"/patient/api/slots?doctor_id=1&date={sunday}").get_json()["closed"] or ""))

appt = one("SELECT appointment_id FROM appointments WHERE appointment_date = %s AND appointment_time = '16:00' AND doctor_id = 1", (FUTURE,))
patient.post(f"/patient/appointments/{appt['appointment_id']}/reschedule", data={"appointment_date": LATER, "appointment_time": "15:30"})
moved = one("SELECT status FROM appointments WHERE appointment_id = %s", (appt["appointment_id"],))["status"] == "Cancelled"
new = one("SELECT appointment_id FROM appointments WHERE doctor_id = 1 AND appointment_date = %s AND appointment_time = '15:30' AND status = 'Scheduled'", (LATER,))
check("Update: reschedule cancels the old slot and books the new one (sp_reschedule_appointment)", moved and new)
priya.post("/patient/appointments", data=dict(booking, appointment_date=LATER, appointment_time="16:30"))
r = patient.post(f"/patient/appointments/{new['appointment_id']}/reschedule", data={"appointment_date": LATER, "appointment_time": "16:30"}, follow_redirects=True)
check("Transaction: a rejected reschedule rolls back, the original booking stays",
      b"already booked" in r.data and one("SELECT status FROM appointments WHERE appointment_id = %s", (new["appointment_id"],))["status"] == "Scheduled")
r = patient.get("/patient/records")
rec = one("SELECT record_id FROM medical_records WHERE patient_id = 1 ORDER BY created_at DESC LIMIT 1")
check("Read: printable visit summary", b"Visit summary" in patient.get(f"/patient/records/{rec['record_id']}/print").data)
check("Edge: a patient cannot open another patient's visit summary",
      patient.get(f"/patient/records/{one('SELECT record_id FROM medical_records WHERE patient_id <> 1 LIMIT 1')['record_id']}/print").status_code == 404)
appt = {"appointment_id": new["appointment_id"]}
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
            data={"appointment_id": visit["appointment_id"], "diagnosis": "Test diagnosis", "prescription": "Test Rx", "notes": "",
                  "bp_systolic": "132", "bp_diastolic": "86", "heart_rate": "78", "temperature_c": "37.1", "weight_kg": "71.5"})
check("Update+Create: sp_complete_visit completes appointment and saves record",
      one("SELECT status FROM appointments WHERE appointment_id = %s", (visit["appointment_id"],))["status"] == "Completed"
      and one("SELECT COUNT(*) AS n FROM medical_records WHERE appointment_id = %s", (visit["appointment_id"],))["n"] == 1)
check("Trigger: trg_medical_record_audit logged the new record", one("SELECT COUNT(*) AS n FROM audit_log")["n"] == logs_before + 1)
check("Create: vitals saved with the record", one("SELECT bp_systolic FROM medical_records WHERE appointment_id = %s", (visit["appointment_id"],))["bp_systolic"] == 132)
r = doctor.post(f"/doctor/patients/{visit['patient_id']}/add-record", data={"diagnosis": "Typo test", "heart_rate": "900"}, follow_redirects=True)
check("Edge: impossible vitals rejected by CHECK constraint", b"heart_rate" in r.data and not one("SELECT 1 AS x FROM medical_records WHERE diagnosis = 'Typo test'"))
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
r = patient.post("/patient/appointments", data=dict(booking, doctor_id=doc["doctor_id"], appointment_time="10:00"), follow_redirects=True)
check("Edge: cannot book an inactive doctor", b"not available" in r.data)
admin.post(f"/admin/doctors/{doc['doctor_id']}/edit", data={"full_name": "Dr. Test Renamed", "email": "td2@hospital.com", "specialization": "X",
                                                           "qualification": "MD", "department_id": dept["department_id"], "phone": "1"})
check("Update: admin edits doctor details", one("SELECT full_name FROM doctors WHERE doctor_id = %s", (doc["doctor_id"],))["full_name"] == "Dr. Test Renamed")
admin.post(f"/admin/departments/{dept['department_id']}/rename", data={"name": "Test Dept 2"})
check("Update: admin renames a department", one("SELECT 1 AS x FROM departments WHERE name = 'Test Dept 2'"))
dept = one("SELECT department_id FROM departments WHERE name = 'Test Dept 2'")
admin.post(f"/admin/departments/{dept['department_id']}/delete")
check("Delete: admin deletes department; doctor kept with department NULL (ON DELETE SET NULL)",
      one("SELECT department_id FROM departments WHERE name = 'Test Dept 2'") is None
      and one("SELECT department_id FROM doctors WHERE doctor_id = %s", (doc["doctor_id"],))["department_id"] is None)

# ---- Admin extras: announcements, CSV, SQL console, password reset, patient deactivation ----
admin.post("/admin/announcements", data={"title": "Test notice for patients", "body": "Hello", "audience": "patient"})
check("Create: announcement reaches patients", b"Test notice for patients" in patient.get("/patient/dashboard").data)
check("Edge: patient-only announcement hidden from doctors", b"Test notice for patients" not in doctor.get("/doctor/dashboard").data)
note = one("SELECT announcement_id FROM announcements WHERE title = 'Test notice for patients'")
admin.post(f"/admin/announcements/{note['announcement_id']}/delete")
check("Delete: admin removes the announcement", one("SELECT 1 AS x FROM announcements WHERE title = 'Test notice for patients'") is None)
r = admin.get("/admin/export/appointments.csv?status=Completed")
check("Read: CSV export with filters", r.mimetype == "text/csv" and b"Scheduled" not in r.data and r.data.count(b"\n") > 100)
r = admin.post("/admin/database", data={"sql": "SELECT COUNT(*) AS n FROM patients"})
check("Read: SQL console runs a SELECT", b">1 row<" in r.data.replace(b"\n", b"").replace(b" (first 200)", b"") or b"1 row</h2>" in r.data)
r = admin.post("/admin/database", data={"sql": "DELETE FROM audit_log"})
check("Edge: SQL console refuses a DELETE", b"Query rejected" in r.data and one("SELECT COUNT(*) AS n FROM audit_log")["n"] > 0)
r = admin.post("/admin/database", data={"sql": "WITH x AS (DELETE FROM audit_log RETURNING 1) SELECT * FROM x"})
check("Edge: SQL console read-only transaction blocks a write hidden in a CTE", b"read-only transaction" in r.data and one("SELECT COUNT(*) AS n FROM audit_log")["n"] > 0)
labuser = one("SELECT user_id FROM users WHERE username = 'labamit'")
admin.post(f"/admin/users/{labuser['user_id']}/password", data={"new_password": "newpass9", "back": "/admin/lab-assistants"})
check("Update: admin resets a password", b"Pending Tests" in login("labamit", "newpass9", "lab_assistant")[1].data)
c, _ = login("priya", "patient123", "patient")
c.post("/account/password", data={"current_password": "patient123", "new_password": "priya456", "confirm_password": "priya456"})
check("Update: user changes own password", b"Welcome, Priya Nair" in login("priya", "priya456", "patient")[1].data)
pid = one("SELECT patient_id FROM patients WHERE full_name = 'Ananya Iyer'")
admin.post(f"/admin/patients/{pid['patient_id']}/toggle")
check("Edge: deactivated patient cannot log in", b"Invalid username, password, or role" in login("ananya.iyer", "patient123", "patient")[1].data)

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
raise SystemExit(1 if failed else 0)
