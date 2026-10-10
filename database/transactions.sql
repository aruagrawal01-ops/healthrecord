-- ============================================================
-- Transaction management demo (Review 2)
-- Real-world transaction: a doctor finishes a consultation.
-- The appointment must be marked Completed AND the diagnosis saved
-- AND any lab tests ordered -- all of it, or none of it.
-- Run statement by statement in pgAdmin / psql to show each effect.
-- ============================================================

-- ---------- Demo 1: COMMIT (all steps persist together) ----------
BEGIN;

UPDATE appointments SET status = 'Completed'
WHERE appointment_id = (
    SELECT a.appointment_id FROM appointments a JOIN patients p ON p.patient_id = a.patient_id
    WHERE p.full_name = 'Priya Nair' AND a.status = 'Scheduled'
    ORDER BY a.appointment_date LIMIT 1);

INSERT INTO medical_records (patient_id, doctor_id, appointment_id, diagnosis, prescription)
SELECT a.patient_id, a.doctor_id, a.appointment_id, 'Stable, review in one month', 'Continue current medication'
FROM appointments a JOIN patients p ON p.patient_id = a.patient_id
WHERE p.full_name = 'Priya Nair' AND a.status = 'Completed'
ORDER BY a.appointment_date DESC LIMIT 1;

COMMIT;
-- Both changes are now durable, and trg_medical_record_audit has logged the insert:
SELECT * FROM audit_log ORDER BY log_id DESC LIMIT 1;


-- ---------- Demo 2: ROLLBACK (undo a mistake completely) ----------
SELECT COUNT(*) AS pending_before FROM lab_tests WHERE status = 'Pending';

BEGIN;
DELETE FROM lab_tests WHERE status = 'Pending';      -- accidental mass delete
SELECT COUNT(*) AS pending_inside FROM lab_tests WHERE status = 'Pending';   -- 0 inside the transaction
ROLLBACK;

SELECT COUNT(*) AS pending_after FROM lab_tests WHERE status = 'Pending';    -- back to the original count


-- ---------- Demo 3: SAVEPOINT (undo only part of the work) ----------
BEGIN;

INSERT INTO lab_tests (patient_id, doctor_id, test_name)
SELECT p.patient_id, d.doctor_id, 'Complete Blood Count'
FROM patients p, doctors d WHERE p.full_name = 'Priya Nair' AND d.full_name = 'Dr. Rajveer Singh';

SAVEPOINT after_cbc;

INSERT INTO lab_tests (patient_id, doctor_id, test_name)
SELECT p.patient_id, d.doctor_id, 'Thyroid Profile'          -- wrong test ordered
FROM patients p, doctors d WHERE p.full_name = 'Priya Nair' AND d.full_name = 'Dr. Rajveer Singh';

ROLLBACK TO SAVEPOINT after_cbc;                            -- drops only the Thyroid order

INSERT INTO lab_tests (patient_id, doctor_id, test_name)
SELECT p.patient_id, d.doctor_id, 'MRI Knee'                 -- the correct test
FROM patients p, doctors d WHERE p.full_name = 'Priya Nair' AND d.full_name = 'Dr. Rajveer Singh';

COMMIT;

-- CBC and MRI Knee are saved; Thyroid Profile never was:
SELECT lt.test_name, lt.status FROM lab_tests lt JOIN patients p ON p.patient_id = lt.patient_id
WHERE p.full_name = 'Priya Nair' AND lt.requested_at::date = CURRENT_DATE
ORDER BY lt.lab_test_id;


-- ---------- Demo 4: automatic rollback on error (atomicity) ----------
-- sp_complete_visit updates the appointment, then inserts the record.
-- NULL diagnosis violates NOT NULL, so the UPDATE is undone too.
SELECT appointment_id, status FROM appointments WHERE status = 'Scheduled' ORDER BY appointment_id LIMIT 1;

DO $$
DECLARE a RECORD;
BEGIN
    SELECT appointment_id, doctor_id INTO a FROM appointments
    WHERE status = 'Scheduled' ORDER BY appointment_id LIMIT 1;
    CALL sp_complete_visit(a.appointment_id, a.doctor_id, NULL, NULL, NULL);
END $$;
-- ERROR: null value in column "diagnosis" ... violates not-null constraint

SELECT appointment_id, status FROM appointments WHERE status = 'Scheduled' ORDER BY appointment_id LIMIT 1;
-- Same appointment, still Scheduled: the UPDATE inside the procedure was rolled back.

-- ACID in this case study:
--  Atomicity   - status change + diagnosis + lab orders commit together or not at all.
--  Consistency - PK/FK/CHECK/NOT NULL and uq_doctor_slot reject invalid states.
--  Isolation   - concurrent bookings of one slot: uq_doctor_slot lets only one commit.
--  Durability  - after COMMIT, Neon's write-ahead log keeps the record across restarts.
