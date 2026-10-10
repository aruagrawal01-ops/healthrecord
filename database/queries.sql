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

-- ============================================================
-- Review 2 additions
-- ============================================================

-- 10. GROUP BY + HAVING: departments with more than one completed visit
SELECT dep.name AS department, COUNT(*) AS completed_visits
FROM appointments a
JOIN doctors d ON a.doctor_id = d.doctor_id
JOIN departments dep ON d.department_id = dep.department_id
WHERE a.status = 'Completed'
GROUP BY dep.name
HAVING COUNT(*) > 1
ORDER BY completed_visits DESC;

-- 11. Correlated subquery: each patient's most recent diagnosis
SELECT p.full_name, mr.diagnosis, mr.created_at::date AS on_date
FROM patients p
JOIN medical_records mr ON mr.patient_id = p.patient_id
WHERE mr.created_at = (SELECT MAX(created_at) FROM medical_records WHERE patient_id = p.patient_id)
ORDER BY p.full_name;

-- 12. EXISTS: patients with at least one lab test still pending
SELECT p.full_name, p.phone
FROM patients p
WHERE EXISTS (SELECT 1 FROM lab_tests lt WHERE lt.patient_id = p.patient_id AND lt.status = 'Pending');

-- 13. LEFT JOIN + COALESCE: every lab assistant's workload (0 if none)
SELECT la.full_name, COALESCE(COUNT(lr.report_id), 0) AS reports_uploaded
FROM lab_assistants la
LEFT JOIN lab_reports lr ON lr.lab_assistant_id = la.lab_assistant_id
GROUP BY la.full_name;

-- 14. SQL functions: user-defined + built-in
SELECT full_name, fn_patient_age(dob) AS age, UPPER(blood_group) AS blood_group,
       CASE WHEN fn_patient_age(dob) < 18 THEN 'Minor' ELSE 'Adult' END AS category
FROM patients ORDER BY age DESC;

SELECT full_name, fn_doctor_load(doctor_id, CURRENT_DATE) AS bookings_today FROM doctors;

-- 15. Aggregate functions together: appointment statistics
SELECT COUNT(*) AS total, MIN(appointment_date) AS first_visit, MAX(appointment_date) AS last_visit,
       ROUND(AVG(fn_patient_age(p.dob)), 1) AS avg_patient_age
FROM appointments a JOIN patients p ON p.patient_id = a.patient_id;

-- 16. Stored procedures (errors are intentional -- they show the validation)
CALL sp_book_appointment(1, 1, CURRENT_DATE + 30, '16:00', 'Routine check-up');   -- succeeds
CALL sp_book_appointment(2, 1, CURRENT_DATE + 30, '16:00', 'Clash');              -- ERROR: already booked
CALL sp_book_appointment(2, 1, CURRENT_DATE - 1, '16:00', 'Past');                -- ERROR: date in the past
