-- ============================================================
-- Bulk demo data: run after seed_data.sql.
-- Generates a realistic hospital: 11 departments, 20 doctors, 4 lab
-- assistants, 80 patients and about six months of visits, with
-- diagnoses, vitals, lab tests and reports to match each specialty.
--
-- Deterministic: no random(). Every rebuild produces the same rows,
-- dated relative to the day it runs (so "today" always has a clinic).
-- Passwords: doctors doctor123, lab staff lab123, patients patient123.
-- ============================================================

INSERT INTO departments (name) VALUES
    ('Pediatrics'), ('Dermatology'), ('Neurology'), ('ENT'), ('Gynecology'), ('Ophthalmology'), ('Psychiatry');

-- ---------- Doctors: two per clinical department ----------
WITH data(username, full_name, specialization, qualification, dept, phone) AS (VALUES
    ('drreddy', 'Dr. Arjun Reddy', 'Interventional Cardiologist', 'MBBS, DM (Cardiology)', 'Cardiology', '9876500014'),
    ('drbose', 'Dr. Ishita Bose', 'Sports Medicine Specialist', 'MBBS, MS (Ortho)', 'Orthopedics', '9876500016'),
    ('drjoshi', 'Dr. Kavita Joshi', 'General Physician', 'MBBS, MD (Medicine)', 'General Medicine', '9876500013'),
    ('drdas', 'Dr. Suresh Das', 'Internal Medicine', 'MBBS, MD (Medicine)', 'General Medicine', '9876500017'),
    ('drkapoor', 'Dr. Neha Kapoor', 'Pediatrician', 'MBBS, MD (Pediatrics)', 'Pediatrics', '9876500011'),
    ('drnair', 'Dr. Meenakshi Nair', 'Neonatologist', 'MBBS, DM (Neonatology)', 'Pediatrics', '9876500018'),
    ('drverma', 'Dr. Sanjay Verma', 'Dermatologist', 'MBBS, MD (Dermatology)', 'Dermatology', '9876500012'),
    ('drkhan', 'Dr. Imran Khan', 'Cosmetic Dermatologist', 'MBBS, DDVL', 'Dermatology', '9876500019'),
    ('drrao', 'Dr. Vikram Rao', 'Neurologist', 'MBBS, DM (Neurology)', 'Neurology', '9876500020'),
    ('drpillai', 'Dr. Lakshmi Pillai', 'Neurophysiologist', 'MBBS, DM (Neurology)', 'Neurology', '9876500021'),
    ('drsharma', 'Dr. Rohit Sharma', 'ENT Specialist', 'MBBS, MS (ENT)', 'ENT', '9876500022'),
    ('drgupta', 'Dr. Pooja Gupta', 'Head and Neck Surgeon', 'MBBS, MS (ENT)', 'ENT', '9876500023'),
    ('drmenon', 'Dr. Anjali Menon', 'Gynecologist', 'MBBS, MS (OBG)', 'Gynecology', '9876500024'),
    ('drsaxena', 'Dr. Ritu Saxena', 'Obstetrician', 'MBBS, DGO', 'Gynecology', '9876500025'),
    ('driyer', 'Dr. Karthik Iyer', 'Ophthalmologist', 'MBBS, MS (Ophthalmology)', 'Ophthalmology', '9876500026'),
    ('drchawla', 'Dr. Neeraj Chawla', 'Retina Specialist', 'MBBS, MS, FRCS', 'Ophthalmology', '9876500027'),
    ('drsen', 'Dr. Arnab Sen', 'Psychiatrist', 'MBBS, MD (Psychiatry)', 'Psychiatry', '9876500028'),
    ('drfernandes', 'Dr. Clara Fernandes', 'Clinical Psychiatrist', 'MBBS, DPM', 'Psychiatry', '9876500029')
), ins AS (
    INSERT INTO users (username, email, password_hash, role)
    SELECT username, substr(username, 3) || '@hospital.com',
           'scrypt:32768:8:1$ea0YADLSQf0nRqBr$b9160fd03f63bb68821664d17ed4c199a21e5d9ce90351e93910fb85cb0e7b673539a89099261ff944549f01670fe4c6c52e3728a654ad29c7a992bd8b8f204b',
           'doctor'
    FROM data RETURNING user_id, username
)
INSERT INTO doctors (user_id, full_name, specialization, qualification, department_id, phone)
SELECT ins.user_id, d.full_name, d.specialization, d.qualification, dep.department_id, d.phone
FROM ins JOIN data d USING (username) JOIN departments dep ON dep.name = d.dept
ORDER BY d.username;

-- ---------- Lab assistants ----------
WITH data(username, full_name, phone) AS (VALUES
    ('labamit', 'Amit Desai', '9876500015'), ('labpriti', 'Priti Kulkarni', '9876500030'), ('labjohn', 'John Mathew', '9876500031')
), ins AS (
    INSERT INTO users (username, email, password_hash, role)
    SELECT username, substr(username, 4) || '@hospital.com',
           'scrypt:32768:8:1$7GusUdB0DGL45fTZ$4c4d31591927b79896997b753aa53626b5a1c47e0511cb5c85c1b5de94f34aa06e5f4348f471c482b2d66ac6676aa07d634b873c6e29d4d221c5e2a761f55739',
           'lab_assistant'
    FROM data RETURNING user_id, username
)
INSERT INTO lab_assistants (user_id, full_name, phone)
SELECT ins.user_id, d.full_name, d.phone FROM ins JOIN data d USING (username) ORDER BY d.username;

-- ---------- 78 more patients from name combinations ----------
-- Even i -> female name, odd i -> male name; every full name is unique.
WITH lists AS (
    SELECT
        ARRAY['Ananya','Meera','Sneha','Fatima','Divya','Kavya','Aisha','Pooja','Riya','Sana','Neha','Shreya','Tanvi',
              'Isha','Nandini','Aditi','Pallavi','Zoya','Simran','Lavanya','Swati','Bhavna','Rekha','Sunita','Geeta',
              'Anjali','Deepika','Kritika','Mansi','Nisha','Payal','Rashmi','Sakshi','Tara','Uma','Vidya','Yamini','Jaya','Komal'] AS fem,
        ARRAY['Vikas','Arjun','Rohan','Karan','Aditya','Siddharth','Amit','Nikhil','Varun','Kunal','Manish','Rajesh','Suresh',
              'Ajay','Vivek','Harsh','Yash','Dev','Kabir','Aryan','Ishaan','Pranav','Sameer','Tarun','Gaurav','Abhishek',
              'Deepak','Mohit','Naveen','Omkar','Prakash','Ravi','Sachin','Tushar','Uday','Vinod','Zubin','Farhan','Lokesh'] AS mal,
        ARRAY['Iyer','Gupta','Pillai','Malhotra','Kulkarni','Das','Sheikh','Mehra','Reddy','Banerjee','Menon','Jain','Patel',
              'Chopra','Rao','Bhat','Kapoor','Shah','Mishra','Yadav','Agarwal','Naidu','Joshi','Thakur','Sinha','Bose',
              'Kaur','Fernandes','Hegde','Dubey'] AS sur,
        ARRAY['MG Road','Park Street','Anna Nagar','Civil Lines','FC Road','Salt Lake','Banjara Hills','Model Town',
              'Marine Drive','Vastrapur','Linking Road','Hazratganj','Indiranagar','Koramangala','Jubilee Hills'] AS streets,
        ARRAY['Chennai','Jaipur','Bengaluru','Ludhiana','Pune','Kolkata','Hyderabad','Chandigarh','Kochi','Ahmedabad',
              'Mumbai','Delhi','Lucknow','Indore','Bhopal','Nagpur','Surat','Vellore','Mysuru','Guwahati'] AS cities,
        ARRAY['O+','B+','A+','O+','B+','AB+','A-','O-','B-','AB-'] AS blood
), people AS (
    SELECT i,
           CASE WHEN i % 2 = 0 THEN fem[i / 2 + 1] ELSE mal[i / 2 + 1] END AS first_name,
           sur[(i * 7 + i / 2) % 30 + 1] AS last_name,
           CASE WHEN i % 2 = 0 THEN 'Female' ELSE 'Male' END AS gender,
           (DATE '2026-01-01' - make_interval(years => 2 + (i * 37) % 83, days => (i * 53) % 360))::DATE AS dob,
           blood[(i * 5) % 10 + 1] AS blood_group,
           '9' || lpad((812345670 + i * 13579)::TEXT, 9, '0') AS phone,
           '9' || lpad((712345670 + i * 24681)::TEXT, 9, '0') AS emergency_contact,
           (1 + (i * 17) % 120) || ', ' || streets[(i * 3) % 15 + 1] || ', ' || cities[(i * 7) % 20 + 1] AS address
    FROM generate_series(0, 77) AS i, lists
), named AS (
    SELECT *, lower(first_name || '.' || last_name) AS username FROM people
), ins AS (
    INSERT INTO users (username, email, password_hash, role)
    SELECT username, username || '@example.com',
           'scrypt:32768:8:1$frE8beitIdVz08EO$ce6b2f041cbf9a2b6d006592935483ddef2d2b31a3f636929761ede2288813f827f603a17705430710db6cde16fc499cb1794bb1a4255e5ec0caf8b692a6622c',
           'patient'
    FROM named ORDER BY i
    RETURNING user_id, username
)
INSERT INTO patients (user_id, full_name, dob, gender, blood_group, phone, address, emergency_contact)
SELECT ins.user_id, n.first_name || ' ' || n.last_name, n.dob, n.gender, n.blood_group, n.phone, n.address, n.emergency_contact
FROM ins JOIN named n USING (username)
ORDER BY n.i;

-- ---------- What a visit to each department looks like ----------
CREATE TEMP TABLE demo_visit_map (dept TEXT, k INT, reason TEXT, diagnosis TEXT, prescription TEXT, notes TEXT, test TEXT, fever BOOLEAN);
INSERT INTO demo_visit_map VALUES
    ('General Medicine', 1, 'Fever and cough', 'Viral upper respiratory infection', 'Paracetamol 500 mg thrice daily for 3 days; steam inhalation', 'Rest and fluids; return if fever lasts beyond 3 days.', 'Complete Blood Count', TRUE),
    ('General Medicine', 2, 'Routine check-up', 'Healthy adult, no acute findings', 'Vitamin D3 60,000 IU weekly for 8 weeks', 'Annual review advised.', 'Vitamin D (25-OH)', FALSE),
    ('General Medicine', 3, 'Fatigue and weight loss', 'Type 2 diabetes mellitus, newly diagnosed', 'Metformin 500 mg twice daily after meals', 'Diet counselling; recheck HbA1c in 3 months.', 'HbA1c', FALSE),
    ('Cardiology', 1, 'Chest discomfort', 'Mild hypertension', 'Amlodipine 5 mg once daily', 'Low-salt diet; monitor BP at home.', 'ECG', FALSE),
    ('Cardiology', 2, 'Palpitations', 'Benign sinus tachycardia', 'Propranolol 10 mg as needed', 'Reduce caffeine; review in 4 weeks.', '2D Echo', FALSE),
    ('Cardiology', 3, 'Breathlessness on exertion', 'Stable angina', 'Aspirin 75 mg daily; atorvastatin 20 mg at night', 'Stress test scheduled.', 'Lipid Profile', FALSE),
    ('Orthopedics', 1, 'Back pain', 'Lumbar muscle strain', 'Ibuprofen 400 mg twice daily after food for 5 days', 'Physiotherapy and posture correction.', 'X-Ray Lumbar Spine', FALSE),
    ('Orthopedics', 2, 'Knee pain', 'Early osteoarthritis of the knee', 'Paracetamol 650 mg as needed; glucosamine 1500 mg daily', 'Quadriceps strengthening exercises.', 'X-Ray Knee', FALSE),
    ('Orthopedics', 3, 'Ankle sprain', 'Grade I lateral ankle sprain', 'Rest, ice, compression; diclofenac gel', 'Ankle support for 2 weeks.', NULL, FALSE),
    ('Pediatrics', 1, 'Fever in child', 'Acute viral fever', 'Paracetamol syrup 15 mg/kg every 6 hours as needed', 'Plenty of fluids; review if fever lasts beyond 48 hours.', 'Complete Blood Count', TRUE),
    ('Pediatrics', 2, 'Vaccination visit', 'Routine immunisation, healthy child', 'As per immunisation schedule', 'Next dose due in 4 weeks.', NULL, FALSE),
    ('Pediatrics', 3, 'Cough and cold', 'Acute bronchitis', 'Salbutamol syrup 2 mg thrice daily for 5 days', 'Steam inhalation; avoid cold drinks.', 'Chest X-Ray', TRUE),
    ('Dermatology', 1, 'Skin rash', 'Allergic contact dermatitis', 'Cetirizine 10 mg at night for 7 days; hydrocortisone 1% cream', 'Avoid new detergents and cosmetics.', 'Serum IgE', FALSE),
    ('Dermatology', 2, 'Acne', 'Acne vulgaris, moderate', 'Adapalene 0.1% gel at night; doxycycline 100 mg daily', 'Gentle face wash; no picking.', NULL, FALSE),
    ('Dermatology', 3, 'Hair fall', 'Telogen effluvium', 'Biotin 10 mg daily; minoxidil 5% solution', 'Review in 3 months.', 'Thyroid Profile (TSH)', FALSE),
    ('Neurology', 1, 'Headache and dizziness', 'Tension-type headache', 'Naproxen 250 mg as needed, max twice daily', 'Sleep hygiene; reduce screen time.', 'MRI Brain', FALSE),
    ('Neurology', 2, 'Migraine', 'Migraine without aura', 'Sumatriptan 50 mg at onset; propranolol 20 mg daily', 'Headache diary advised.', NULL, FALSE),
    ('Neurology', 3, 'Numbness in hands', 'Carpal tunnel syndrome', 'Wrist splint at night; vitamin B12 1500 mcg daily', 'Nerve conduction study ordered.', 'Vitamin B12', FALSE),
    ('ENT', 1, 'Ear pain', 'Acute otitis media', 'Amoxicillin 500 mg thrice daily for 5 days', 'Keep the ear dry.', NULL, FALSE),
    ('ENT', 2, 'Sore throat', 'Acute pharyngitis', 'Azithromycin 500 mg daily for 3 days; warm saline gargles', 'Review if not better in 3 days.', 'Throat Swab Culture', TRUE),
    ('ENT', 3, 'Blocked nose', 'Allergic rhinitis', 'Fluticasone nasal spray twice daily; montelukast 10 mg at night', 'Avoid dust exposure.', 'Absolute Eosinophil Count', FALSE),
    ('Gynecology', 1, 'Irregular periods', 'Polycystic ovary syndrome', 'Metformin 500 mg twice daily; lifestyle changes', 'Weight management advised.', 'Pelvic Ultrasound', FALSE),
    ('Gynecology', 2, 'Antenatal check-up', 'Normal pregnancy, routine review', 'Folic acid 5 mg; iron and calcium supplements', 'Next scan in 4 weeks.', 'Hemoglobin', FALSE),
    ('Gynecology', 3, 'Lower abdominal pain', 'Urinary tract infection', 'Nitrofurantoin 100 mg twice daily for 5 days', 'Increase water intake.', 'Urine Culture', FALSE),
    ('Ophthalmology', 1, 'Blurred vision', 'Myopia', 'Spectacles prescribed (-1.75 D both eyes)', 'Annual eye check.', NULL, FALSE),
    ('Ophthalmology', 2, 'Red eyes', 'Allergic conjunctivitis', 'Olopatadine 0.1% eye drops twice daily', 'Avoid rubbing the eyes.', NULL, FALSE),
    ('Ophthalmology', 3, 'Diabetic eye screening', 'Mild non-proliferative diabetic retinopathy', 'Tight glucose control; review in 6 months', 'Fundus photographs documented.', 'Fasting Blood Sugar', FALSE),
    ('Psychiatry', 1, 'Trouble sleeping', 'Primary insomnia', 'Melatonin 3 mg at night; sleep hygiene', 'CBT for insomnia recommended.', NULL, FALSE),
    ('Psychiatry', 2, 'Anxiety', 'Generalised anxiety disorder', 'Escitalopram 10 mg daily', 'Weekly therapy sessions.', 'Thyroid Profile (TSH)', FALSE),
    ('Psychiatry', 3, 'Low mood', 'Mild depressive episode', 'Sertraline 50 mg daily', 'Follow up in 2 weeks.', NULL, FALSE);

-- One result per test name (the same test always reports the same way here)
CREATE TEMP TABLE demo_test_result (test TEXT PRIMARY KEY, result TEXT);
INSERT INTO demo_test_result VALUES
    ('Complete Blood Count', 'Hb 12.9 g/dL, WBC 10,400/uL, platelets 2.6 lakh/uL - within normal limits'),
    ('Vitamin D (25-OH)', '25-OH Vitamin D 18 ng/mL - insufficient'),
    ('HbA1c', 'HbA1c 7.4% - diabetic range'),
    ('ECG', 'Normal sinus rhythm, no ST changes'),
    ('2D Echo', 'Normal LV function, EF 60%'),
    ('Lipid Profile', 'Total cholesterol 232 mg/dL, LDL 158 mg/dL - high'),
    ('X-Ray Lumbar Spine', 'No fracture; mild loss of lumbar lordosis'),
    ('X-Ray Knee', 'Mild joint space narrowing, no fracture'),
    ('Chest X-Ray', 'No consolidation; mild bronchial markings'),
    ('Serum IgE', 'Total IgE 240 IU/mL - elevated'),
    ('Thyroid Profile (TSH)', 'TSH 2.1 mIU/L - normal'),
    ('MRI Brain', 'No intracranial abnormality detected'),
    ('Vitamin B12', 'Vitamin B12 180 pg/mL - low'),
    ('Throat Swab Culture', 'No pathogenic growth'),
    ('Absolute Eosinophil Count', 'AEC 620 cells/uL - raised'),
    ('Pelvic Ultrasound', 'Bilateral polycystic ovaries'),
    ('Hemoglobin', 'Hb 10.9 g/dL - mild anaemia'),
    ('Urine Culture', 'E. coli > 10^5 CFU/mL, sensitive to nitrofurantoin'),
    ('Fasting Blood Sugar', 'FBS 148 mg/dL - high');

-- ---------- Appointments: about six months back, three weeks ahead ----------
-- Every (doctor, day, slot) combination is visited once and kept when a fixed
-- arithmetic test passes (~3.4%), so no doctor is ever double-booked.
-- Pediatrics only sees children, Gynecology only women, the rest adults.
-- General Medicine, Pediatrics and Cardiology are busier (weight 2: twice the slots).
WITH pools AS (
    SELECT ARRAY(SELECT patient_id FROM patients WHERE fn_patient_age(dob) < 16 ORDER BY patient_id) AS kids,
           ARRAY(SELECT patient_id FROM patients WHERE gender = 'Female' AND fn_patient_age(dob) >= 18 ORDER BY patient_id) AS women,
           ARRAY(SELECT patient_id FROM patients WHERE fn_patient_age(dob) >= 16 ORDER BY patient_id) AS adults
), docs AS (
    SELECT d.doctor_id, dep.name AS dept, (ROW_NUMBER() OVER (ORDER BY d.doctor_id) - 1)::INT AS di,
           CASE WHEN dep.name IN ('General Medicine', 'Pediatrics', 'Cardiology') THEN 2 ELSE 1 END AS w
    FROM doctors d JOIN departments dep ON dep.department_id = d.department_id
), grid AS (
    SELECT docs.*, day, slot, (CURRENT_DATE - 180 + day) AS appt_date,
           (TIME '09:00' + (slot + CASE WHEN slot >= 8 THEN 2 ELSE 0 END) * INTERVAL '30 minutes')::TIME AS appt_time,
           (di * 31 + day * 17 + slot * 13) AS h
    FROM docs, generate_series(0, 201) AS day, generate_series(0, 13) AS slot
), picked AS (
    SELECT g.*, (h / 29) AS m,
           CASE WHEN dept = 'Pediatrics' THEN p.kids WHEN dept = 'Gynecology' THEN p.women ELSE p.adults END AS pool
    FROM grid g, pools p
    WHERE h % 29 < w AND EXTRACT(DOW FROM appt_date) <> 0
)
INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason, status, created_at)
SELECT pool[1 + (m * 37 + di * 11 + slot * 3) % cardinality(pool)],
       pk.doctor_id, pk.appt_date, pk.appt_time, vm.reason,
       CASE WHEN pk.appt_date > CURRENT_DATE THEN CASE WHEN m % 13 = 0 THEN 'Cancelled' ELSE 'Scheduled' END
            WHEN pk.appt_date = CURRENT_DATE THEN 'Scheduled'
            ELSE CASE WHEN m % 9 = 0 THEN 'Cancelled' ELSE 'Completed' END END,
       LEAST(pk.appt_date - (1 + m % 10) + TIME '10:00', LOCALTIMESTAMP)
FROM picked pk
JOIN demo_visit_map vm ON vm.dept = pk.dept AND vm.k = (m + di) % 3 + 1
ON CONFLICT (doctor_id, appointment_date, appointment_time) WHERE status <> 'Cancelled' DO NOTHING;

-- Today's clinic for Dr. Mehta (the demo doctor), on top of the generated visits
INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason, status)
SELECT p.patient_id, d.doctor_id, CURRENT_DATE, t.slot, 'Chest discomfort', 'Scheduled'
FROM (SELECT patient_id, ROW_NUMBER() OVER (ORDER BY patient_id) AS r
      FROM patients WHERE fn_patient_age(dob) >= 30 AND full_name <> 'Rahul Sharma') p
JOIN (VALUES (1, TIME '11:30'), (2, TIME '12:00'), (3, TIME '12:30'), (4, TIME '14:30'), (5, TIME '15:30')) AS t(r, slot) ON t.r = p.r
JOIN doctors d ON d.full_name = 'Dr. Anita Mehta'
ON CONFLICT (doctor_id, appointment_date, appointment_time) WHERE status <> 'Cancelled' DO NOTHING;

-- ---------- A medical record, with vitals, for every completed visit ----------
-- Fires trg_medical_record_audit once per row.
INSERT INTO medical_records (patient_id, doctor_id, appointment_id, diagnosis, prescription, notes,
                             bp_systolic, bp_diastolic, heart_rate, temperature_c, weight_kg, created_at)
SELECT a.patient_id, a.doctor_id, a.appointment_id, vm.diagnosis, vm.prescription, vm.notes,
       108 + (a.patient_id * 7 + a.appointment_id) % 32 + CASE WHEN vm.diagnosis IN ('Mild hypertension', 'Stable angina') THEN 22 ELSE 0 END,
       68 + (a.patient_id * 3 + a.appointment_id) % 18 + CASE WHEN vm.diagnosis IN ('Mild hypertension', 'Stable angina') THEN 12 ELSE 0 END,
       64 + (a.patient_id * 5 + a.appointment_id * 3) % 26 + CASE WHEN fn_patient_age(p.dob) < 16 THEN 22 ELSE 0 END,
       36.5 + (a.appointment_id % 6) / 10.0 + CASE WHEN vm.fever THEN 1.6 ELSE 0 END,
       CASE WHEN fn_patient_age(p.dob) < 16 THEN 10 + fn_patient_age(p.dob) * 3
            ELSE 50 + (a.patient_id * 13) % 36 END + ((a.appointment_id % 5) - 2) * 0.4,
       a.appointment_date + a.appointment_time + INTERVAL '20 minutes'
FROM appointments a
JOIN patients p ON p.patient_id = a.patient_id
JOIN doctors d ON d.doctor_id = a.doctor_id
JOIN departments dep ON dep.department_id = d.department_id
JOIN demo_visit_map vm ON vm.dept = dep.name AND vm.reason = a.reason
WHERE a.status = 'Completed'
  AND NOT EXISTS (SELECT 1 FROM medical_records r WHERE r.appointment_id = a.appointment_id);

-- ---------- Lab tests ordered at about two thirds of the visits that need one ----------
INSERT INTO lab_tests (patient_id, doctor_id, test_name, requested_at)
SELECT a.patient_id, a.doctor_id, vm.test, a.appointment_date + a.appointment_time + INTERVAL '30 minutes'
FROM appointments a
JOIN doctors d ON d.doctor_id = a.doctor_id
JOIN departments dep ON dep.department_id = d.department_id
JOIN demo_visit_map vm ON vm.dept = dep.name AND vm.reason = a.reason
WHERE a.status = 'Completed' AND vm.test IS NOT NULL AND a.appointment_id % 3 <> 0
ORDER BY a.appointment_date, a.appointment_time;

-- Reports for everything except recent tests: the last 3 days, plus about one in seven
-- from the last 12 days, stay in the lab queue so it shows realistic ageing.
-- Turnaround varies from 6 to 45 hours; each insert fires trg_lab_report_insert.
INSERT INTO lab_reports (lab_test_id, lab_assistant_id, result_summary, uploaded_at)
SELECT lt.lab_test_id, la.lab_assistant_id, tr.result, lt.requested_at + (6 + lt.lab_test_id % 40) * INTERVAL '1 hour'
FROM lab_tests lt
JOIN demo_test_result tr ON tr.test = lt.test_name
JOIN (SELECT lab_assistant_id, (ROW_NUMBER() OVER (ORDER BY lab_assistant_id) - 1)::INT AS i FROM lab_assistants) la
  ON la.i = lt.lab_test_id % 4
WHERE lt.status = 'Pending'
  AND lt.requested_at < LOCALTIMESTAMP - INTERVAL '3 days'
  AND NOT (lt.lab_test_id % 7 = 0 AND lt.requested_at > LOCALTIMESTAMP - INTERVAL '12 days');

-- ---------- Announcements ----------
INSERT INTO announcements (title, body, audience, is_pinned, created_by, created_at)
SELECT t.title, t.body, t.audience, t.pinned, u.user_id, LOCALTIMESTAMP - t.age
FROM (VALUES
    ('Free health camp this Saturday', 'Free BP, blood sugar and eye screening in the main lobby, 9 am to 1 pm. Walk-ins welcome.', 'all', TRUE, INTERVAL '1 day'),
    ('New Ophthalmology wing open', 'Retina and diabetic eye screening are now available on the second floor.', 'patient', FALSE, INTERVAL '4 days'),
    ('Mandatory: update clinical notes', 'Please add vitals for every completed visit so patient trend charts stay accurate.', 'doctor', TRUE, INTERVAL '2 days'),
    ('Analyzer maintenance window', 'The biochemistry analyzer is offline on Sunday from 7 to 10 am. Plan sample runs around it.', 'lab_assistant', FALSE, INTERVAL '3 days')
) AS t(title, body, audience, pinned, age)
JOIN users u ON u.username = 'admin';

DROP TABLE demo_visit_map;
DROP TABLE demo_test_result;
