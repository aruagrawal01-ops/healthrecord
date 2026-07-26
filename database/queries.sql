-- ============================================================
-- Sample queries for the project report / viva.
-- Run these in pgAdmin4 (or psql) after schema.sql + seed_data.sql
-- to demonstrate joins, aggregation, subqueries and views.
-- ============================================================

-- 1. JOIN: full medical history of a specific patient
SELECT p.full_name AS patient, d.full_name AS doctor,
       mr.diagnosis, mr.prescription, mr.created_at
FROM medical_records mr
JOIN patients p ON mr.patient_id = p.patient_id
JOIN doctors d ON mr.doctor_id = d.doctor_id
WHERE p.full_name = 'Rahul Sharma'
ORDER BY mr.created_at DESC;

-- 2. JOIN + WHERE: today's appointment schedule for a doctor
SELECT a.appointment_time, p.full_name AS patient, a.reason, a.status
FROM appointments a
JOIN patients p ON a.patient_id = p.patient_id
JOIN doctors d ON a.doctor_id = d.doctor_id
WHERE d.full_name = 'Dr. Anita Mehta' AND a.appointment_date = CURRENT_DATE
ORDER BY a.appointment_time;

-- 3. Aggregate: number of patients handled by each doctor
SELECT d.full_name AS doctor, COUNT(DISTINCT a.patient_id) AS patients_seen
FROM doctors d
LEFT JOIN appointments a ON a.doctor_id = d.doctor_id
GROUP BY d.full_name
ORDER BY patients_seen DESC;

-- 4. Aggregate: appointment status breakdown
SELECT status, COUNT(*) AS total
FROM appointments
GROUP BY status;

-- 5. Subquery: patients who have never had a lab test requested
SELECT full_name FROM patients
WHERE patient_id NOT IN (SELECT DISTINCT patient_id FROM lab_tests);

-- 6. Subquery: doctors whose patient count is above the average
SELECT full_name, patients_seen FROM (
    SELECT d.full_name, COUNT(DISTINCT a.patient_id) AS patients_seen
    FROM doctors d
    LEFT JOIN appointments a ON a.doctor_id = d.doctor_id
    GROUP BY d.full_name
) sub
WHERE patients_seen > (
    SELECT AVG(cnt) FROM (
        SELECT COUNT(DISTINCT patient_id) AS cnt FROM appointments GROUP BY doctor_id
    ) avg_sub
);

-- 7. Using the pre-built views (see schema.sql)
SELECT * FROM view_patient_history;
SELECT * FROM view_doctor_schedule WHERE status = 'Scheduled';
SELECT * FROM view_pending_lab_tests;
SELECT * FROM view_admin_stats;

-- 8. Multi-table JOIN: lab report turnaround (requested -> uploaded)
SELECT p.full_name AS patient, lt.test_name, la.full_name AS lab_assistant,
       lt.requested_at, lr.uploaded_at,
       (lr.uploaded_at - lt.requested_at) AS turnaround_time
FROM lab_reports lr
JOIN lab_tests lt ON lr.lab_test_id = lt.lab_test_id
JOIN patients p ON lt.patient_id = p.patient_id
JOIN lab_assistants la ON lr.lab_assistant_id = la.lab_assistant_id;

-- 9. Trigger demonstration: inserting into lab_reports auto-updates
--    lab_tests.status to 'Completed' (see trg_lab_report_insert).
--    Before:
SELECT status FROM lab_tests WHERE test_name = 'Lipid Profile';
--    INSERT INTO lab_reports (...) VALUES (...);   -- fired from the app
--    After the insert, re-run the SELECT above -> status is now 'Completed'.
