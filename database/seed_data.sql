-- ============================================================
-- Sample data for demo / viva.
-- All demo accounts use the password shown in the comment next
-- to them (already hashed below with werkzeug's scrypt hasher,
-- the same one app.py uses to verify logins).
-- ============================================================

INSERT INTO departments (name) VALUES
    ('General Medicine'),
    ('Cardiology'),
    ('Orthopedics'),
    ('Pathology');

-- password: admin123
INSERT INTO users (username, email, password_hash, role) VALUES
    ('admin', 'admin@hospital.com',
     'scrypt:32768:8:1$m9FFe72f7VFrGLtX$148ee570e29cbde6cf5f4ac2e73904be2189a28c3c082db94d1bd513e04fe8b42c386a119600a0c9e7566f4e202693e2718feda426df9af70c2759c200bd490e',
     'admin');

INSERT INTO admins (user_id, full_name)
SELECT user_id, 'System Administrator' FROM users WHERE username = 'admin';

-- password: doctor123 (both doctors)
INSERT INTO users (username, email, password_hash, role) VALUES
    ('drmehta', 'mehta@hospital.com',
     'scrypt:32768:8:1$ea0YADLSQf0nRqBr$b9160fd03f63bb68821664d17ed4c199a21e5d9ce90351e93910fb85cb0e7b673539a89099261ff944549f01670fe4c6c52e3728a654ad29c7a992bd8b8f204b',
     'doctor'),
    ('drsingh', 'singh@hospital.com',
     'scrypt:32768:8:1$ea0YADLSQf0nRqBr$b9160fd03f63bb68821664d17ed4c199a21e5d9ce90351e93910fb85cb0e7b673539a89099261ff944549f01670fe4c6c52e3728a654ad29c7a992bd8b8f204b',
     'doctor');

INSERT INTO doctors (user_id, full_name, specialization, qualification, department_id, phone)
SELECT u.user_id, 'Dr. Anita Mehta', 'Cardiologist', 'MBBS, MD (Cardiology)', d.department_id, '9876500001'
FROM users u, departments d WHERE u.username = 'drmehta' AND d.name = 'Cardiology';

INSERT INTO doctors (user_id, full_name, specialization, qualification, department_id, phone)
SELECT u.user_id, 'Dr. Rajveer Singh', 'Orthopedic Surgeon', 'MBBS, MS (Ortho)', d.department_id, '9876500002'
FROM users u, departments d WHERE u.username = 'drsingh' AND d.name = 'Orthopedics';

-- password: lab123
INSERT INTO users (username, email, password_hash, role) VALUES
    ('labtech', 'labtech@hospital.com',
     'scrypt:32768:8:1$7GusUdB0DGL45fTZ$4c4d31591927b79896997b753aa53626b5a1c47e0511cb5c85c1b5de94f34aa06e5f4348f471c482b2d66ac6676aa07d634b873c6e29d4d221c5e2a761f55739',
     'lab_assistant');

INSERT INTO lab_assistants (user_id, full_name, phone)
SELECT user_id, 'Sunita Rao', '9876500003' FROM users WHERE username = 'labtech';

-- password: patient123 (both patients)
INSERT INTO users (username, email, password_hash, role) VALUES
    ('rahul', 'rahul@example.com',
     'scrypt:32768:8:1$frE8beitIdVz08EO$ce6b2f041cbf9a2b6d006592935483ddef2d2b31a3f636929761ede2288813f827f603a17705430710db6cde16fc499cb1794bb1a4255e5ec0caf8b692a6622c',
     'patient'),
    ('priya', 'priya@example.com',
     'scrypt:32768:8:1$frE8beitIdVz08EO$ce6b2f041cbf9a2b6d006592935483ddef2d2b31a3f636929761ede2288813f827f603a17705430710db6cde16fc499cb1794bb1a4255e5ec0caf8b692a6622c',
     'patient');

INSERT INTO patients (user_id, full_name, dob, gender, blood_group, phone, address, emergency_contact)
SELECT user_id, 'Rahul Sharma', '1995-04-12', 'Male', 'O+', '9876500004', '221B, MG Road, Delhi', '9876500009'
FROM users WHERE username = 'rahul';

INSERT INTO patients (user_id, full_name, dob, gender, blood_group, phone, address, emergency_contact)
SELECT user_id, 'Priya Nair', '1998-09-23', 'Female', 'B+', '9876500005', '14, Park Street, Kochi', '9876500010'
FROM users WHERE username = 'priya';

-- Sample appointments
INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason, status)
SELECT p.patient_id, d.doctor_id, CURRENT_DATE, '10:30', 'Chest pain and shortness of breath', 'Completed'
FROM patients p, doctors d WHERE p.full_name = 'Rahul Sharma' AND d.full_name = 'Dr. Anita Mehta';

INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason, status)
SELECT p.patient_id, d.doctor_id, CURRENT_DATE + 2, '11:00', 'Knee pain follow-up', 'Scheduled'
FROM patients p, doctors d WHERE p.full_name = 'Priya Nair' AND d.full_name = 'Dr. Rajveer Singh';

-- Sample medical record (for the completed appointment)
INSERT INTO medical_records (patient_id, doctor_id, appointment_id, diagnosis, prescription, notes)
SELECT p.patient_id, d.doctor_id, a.appointment_id,
       'Mild hypertension', 'Amlodipine 5mg once daily for 2 weeks',
       'Advised low-sodium diet and follow-up in 2 weeks.'
FROM patients p
JOIN doctors d ON d.full_name = 'Dr. Anita Mehta'
JOIN appointments a ON a.patient_id = p.patient_id AND a.doctor_id = d.doctor_id
WHERE p.full_name = 'Rahul Sharma';

-- Sample lab test request (still pending -> shows up for the lab assistant)
INSERT INTO lab_tests (patient_id, doctor_id, test_name, status)
SELECT p.patient_id, d.doctor_id, 'Lipid Profile', 'Pending'
FROM patients p, doctors d WHERE p.full_name = 'Rahul Sharma' AND d.full_name = 'Dr. Anita Mehta';
