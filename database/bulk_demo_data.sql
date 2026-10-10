-- ============================================================
-- Bulk demo data: run after seed_data.sql.
-- Deterministic (no random()), so the demo queries in queries.sql
-- give the same results every time the database is rebuilt.
-- Passwords: doctors doctor123, lab staff lab123, patients patient123.
-- ============================================================

INSERT INTO departments (name) VALUES ('Pediatrics'), ('Dermatology'), ('Neurology');

-- More doctors (data-modifying CTE: insert the login, then the profile)
WITH data(username, email, full_name, specialization, qualification, dept, phone) AS (VALUES
    ('drkapoor', 'kapoor@hospital.com', 'Dr. Neha Kapoor', 'Pediatrician', 'MBBS, MD (Pediatrics)', 'Pediatrics', '9876500011'),
    ('drverma', 'verma@hospital.com', 'Dr. Sanjay Verma', 'Dermatologist', 'MBBS, MD (Dermatology)', 'Dermatology', '9876500012'),
    ('drjoshi', 'joshi@hospital.com', 'Dr. Kavita Joshi', 'General Physician', 'MBBS, MD (Medicine)', 'General Medicine', '9876500013'),
    ('drrao', 'rao@hospital.com', 'Dr. Vikram Rao', 'Neurologist', 'MBBS, DM (Neurology)', 'Neurology', '9876500014')
), ins AS (
    INSERT INTO users (username, email, password_hash, role)
    SELECT username, email,
           'scrypt:32768:8:1$ea0YADLSQf0nRqBr$b9160fd03f63bb68821664d17ed4c199a21e5d9ce90351e93910fb85cb0e7b673539a89099261ff944549f01670fe4c6c52e3728a654ad29c7a992bd8b8f204b',
           'doctor'
    FROM data RETURNING user_id, username
)
INSERT INTO doctors (user_id, full_name, specialization, qualification, department_id, phone)
SELECT ins.user_id, d.full_name, d.specialization, d.qualification, dep.department_id, d.phone
FROM ins JOIN data d USING (username) JOIN departments dep ON dep.name = d.dept;

-- Second lab assistant
WITH ins AS (
    INSERT INTO users (username, email, password_hash, role) VALUES
    ('labamit', 'amit@hospital.com',
     'scrypt:32768:8:1$7GusUdB0DGL45fTZ$4c4d31591927b79896997b753aa53626b5a1c47e0511cb5c85c1b5de94f34aa06e5f4348f471c482b2d66ac6676aa07d634b873c6e29d4d221c5e2a761f55739',
     'lab_assistant')
    RETURNING user_id
)
INSERT INTO lab_assistants (user_id, full_name, phone) SELECT user_id, 'Amit Desai', '9876500015' FROM ins;

-- Twelve more patients
WITH data(username, email, full_name, dob, gender, blood_group, phone, address, emergency_contact) AS (VALUES
    ('ananya', 'ananya@example.com', 'Ananya Iyer', DATE '2001-02-14', 'Female', 'A+', '9876500021', '12, Anna Nagar, Chennai', '9876500041'),
    ('vikas', 'vikas@example.com', 'Vikas Gupta', DATE '1988-07-03', 'Male', 'B+', '9876500022', '7, Civil Lines, Jaipur', '9876500042'),
    ('meera', 'meera@example.com', 'Meera Pillai', DATE '1992-11-30', 'Female', 'O-', '9876500023', '45, MG Road, Bengaluru', '9876500043'),
    ('arjun', 'arjun@example.com', 'Arjun Malhotra', DATE '1979-05-19', 'Male', 'AB+', '9876500024', '3, Model Town, Ludhiana', '9876500044'),
    ('sneha', 'sneha@example.com', 'Sneha Kulkarni', DATE '1996-08-08', 'Female', 'A-', '9876500025', '21, FC Road, Pune', '9876500045'),
    ('rohan', 'rohan@example.com', 'Rohan Das', DATE '2010-01-25', 'Male', 'O+', '9876500026', '9, Salt Lake, Kolkata', '9876500046'),
    ('fatima', 'fatima@example.com', 'Fatima Sheikh', DATE '1985-03-12', 'Female', 'B-', '9876500027', '18, Banjara Hills, Hyderabad', '9876500047'),
    ('karan', 'karan@example.com', 'Karan Mehra', DATE '1999-12-01', 'Male', 'A+', '9876500028', '5, Sector 17, Chandigarh', '9876500048'),
    ('divya', 'divya@example.com', 'Divya Reddy', DATE '1990-06-22', 'Female', 'O+', '9876500029', '30, Jubilee Hills, Hyderabad', '9876500049'),
    ('aditya', 'aditya@example.com', 'Aditya Banerjee', DATE '1972-09-15', 'Male', 'B+', '9876500030', '11, Park Circus, Kolkata', '9876500050'),
    ('kavya', 'kavya@example.com', 'Kavya Menon', DATE '2015-04-05', 'Female', 'AB-', '9876500031', '6, Marine Drive, Kochi', '9876500051'),
    ('siddharth', 'siddharth@example.com', 'Siddharth Jain', DATE '1983-10-28', 'Male', 'O+', '9876500032', '22, Vastrapur, Ahmedabad', '9876500052')
), ins AS (
    INSERT INTO users (username, email, password_hash, role)
    SELECT username, email,
           'scrypt:32768:8:1$frE8beitIdVz08EO$ce6b2f041cbf9a2b6d006592935483ddef2d2b31a3f636929761ede2288813f827f603a17705430710db6cde16fc499cb1794bb1a4255e5ec0caf8b692a6622c',
           'patient'
    FROM data RETURNING user_id, username
)
INSERT INTO patients (user_id, full_name, dob, gender, blood_group, phone, address, emergency_contact)
SELECT ins.user_id, d.full_name, d.dob, d.gender, d.blood_group, d.phone, d.address, d.emergency_contact
FROM ins JOIN data d USING (username);

-- Visit types: what each reason leads to (diagnosis, prescription, lab test, result)
CREATE TEMP TABLE demo_visit_map (reason TEXT, diagnosis TEXT, prescription TEXT, notes TEXT, test TEXT, result TEXT);
INSERT INTO demo_visit_map VALUES
    ('Fever and cough', 'Viral upper respiratory infection', 'Paracetamol 500 mg thrice daily for 3 days; steam inhalation', 'Rest and fluids; return if fever lasts beyond 3 days.', 'Complete Blood Count', 'Hb 13.8 g/dL, WBC 9,800/uL, platelets 2.4 lakh/uL - within normal limits'),
    ('Routine check-up', 'Healthy adult, no acute findings', 'Vitamin D3 60,000 IU weekly for 8 weeks', 'Annual review advised.', 'Vitamin D (25-OH)', '25-OH Vitamin D 18 ng/mL - insufficient'),
    ('Back pain', 'Lumbar muscle strain', 'Ibuprofen 400 mg twice daily after food for 5 days', 'Physiotherapy and posture correction.', 'X-Ray Lumbar Spine', 'No fracture; mild loss of lumbar lordosis'),
    ('Skin rash', 'Allergic contact dermatitis', 'Cetirizine 10 mg at night for 7 days; hydrocortisone 1% cream', 'Avoid new detergents and cosmetics.', 'Serum IgE', 'Total IgE 240 IU/mL - elevated'),
    ('Headache and dizziness', 'Tension-type headache', 'Naproxen 250 mg as needed, max twice daily', 'Sleep hygiene; reduce screen time.', 'MRI Brain', 'No intracranial abnormality detected'),
    ('Follow-up visit', 'Condition improving, continue treatment', 'Continue current medication for 2 weeks', 'Review in 2 weeks.', NULL, NULL),
    ('Chest discomfort', 'Mild hypertension', 'Amlodipine 5 mg once daily', 'Low-salt diet; monitor BP at home.', 'ECG', 'Normal sinus rhythm, no ST changes'),
    ('Joint pain', 'Early osteoarthritis of the knee', 'Paracetamol 650 mg as needed; glucosamine 1500 mg daily', 'Quadriceps strengthening exercises.', 'Uric Acid', 'Serum uric acid 5.9 mg/dL - normal');

-- Three appointments per patient: an older visit, a recent visit
-- (every 5th one cancelled) and an upcoming booking. Slots are offset
-- per patient so no doctor is double-booked (uq_doctor_slot).
WITH p AS (SELECT patient_id, ROW_NUMBER() OVER (ORDER BY patient_id)::INT AS r FROM patients),
     d AS (SELECT doctor_id, (ROW_NUMBER() OVER (ORDER BY doctor_id) - 1)::INT AS i, COUNT(*) OVER ()::INT AS n FROM doctors)
INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason, status)
SELECT p.patient_id, d.doctor_id,
       CASE k WHEN 1 THEN CURRENT_DATE - (p.r * 3 + 20) WHEN 2 THEN CURRENT_DATE - (p.r + 5) ELSE CURRENT_DATE + (p.r % 7) + 1 END,
       TIME '09:00' + (p.r - 1) * INTERVAL '20 minutes',
       (ARRAY(SELECT reason FROM demo_visit_map ORDER BY reason))[1 + (p.r + k) % 8],
       CASE WHEN k = 3 THEN 'Scheduled' WHEN k = 2 AND p.r % 5 = 0 THEN 'Cancelled' ELSE 'Completed' END
FROM p CROSS JOIN generate_series(1, 3) AS k
JOIN d ON d.i = (p.r + (k - 1) * 2) % d.n;

-- Today's clinic for Dr. Mehta (shows on her dashboard)
INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason, status)
SELECT p.patient_id, d.doctor_id, CURRENT_DATE, TIME '11:00' + p.r * INTERVAL '30 minutes', 'Chest discomfort', 'Scheduled'
FROM (SELECT patient_id, ROW_NUMBER() OVER (ORDER BY patient_id) AS r FROM patients WHERE full_name <> 'Rahul Sharma') p
JOIN doctors d ON d.full_name = 'Dr. Anita Mehta'
WHERE p.r <= 4;

-- A medical record for every completed visit (fires trg_medical_record_audit)
INSERT INTO medical_records (patient_id, doctor_id, appointment_id, diagnosis, prescription, notes, created_at)
SELECT a.patient_id, a.doctor_id, a.appointment_id, m.diagnosis, m.prescription, m.notes,
       a.appointment_date + a.appointment_time + INTERVAL '20 minutes'
FROM appointments a JOIN demo_visit_map m ON m.reason = a.reason
WHERE a.status = 'Completed'
  AND NOT EXISTS (SELECT 1 FROM medical_records r WHERE r.appointment_id = a.appointment_id);

-- Lab tests ordered during completed visits
INSERT INTO lab_tests (patient_id, doctor_id, test_name, requested_at)
SELECT a.patient_id, a.doctor_id, m.test, a.appointment_date + a.appointment_time + INTERVAL '30 minutes'
FROM appointments a JOIN demo_visit_map m ON m.reason = a.reason
WHERE a.status = 'Completed' AND m.test IS NOT NULL;

-- Reports for tests older than 10 days; the rest stay in the lab queue.
-- Inserting a report fires trg_lab_report_insert, which marks the test Completed.
INSERT INTO lab_reports (lab_test_id, lab_assistant_id, result_summary, uploaded_at)
SELECT lt.lab_test_id, la.lab_assistant_id, m.result, lt.requested_at + INTERVAL '1 day'
FROM lab_tests lt
JOIN demo_visit_map m ON m.test = lt.test_name
JOIN (SELECT lab_assistant_id, (ROW_NUMBER() OVER (ORDER BY lab_assistant_id) - 1)::INT AS i FROM lab_assistants) la
  ON la.i = lt.lab_test_id % 2
WHERE lt.status = 'Pending' AND lt.requested_at < CURRENT_TIMESTAMP - INTERVAL '10 days';

DROP TABLE demo_visit_map;
