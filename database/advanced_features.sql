-- ============================================================
-- Advanced database features (Review 2)
-- Run after schema.sql. Safe to re-run.
--   Procedures: sp_book_appointment, sp_complete_visit, sp_reschedule_appointment
--   Functions:  fn_patient_age, fn_doctor_load, fn_free_slots
--   Triggers:   trg_lab_report_insert (schema.sql), trg_medical_record_audit
--   Views:      6 views in schema.sql
-- ============================================================

-- ------------------------------------------------------------
-- Function 1: patient age in whole years (used on patient lists)
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_patient_age(p_dob DATE)
RETURNS INTEGER
LANGUAGE sql STABLE AS $$
    SELECT EXTRACT(YEAR FROM age(CURRENT_DATE, p_dob))::INTEGER;
$$;

-- ------------------------------------------------------------
-- Function 2: number of live (non-cancelled) bookings a doctor
-- has on a given day (used on the admin doctors page)
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_doctor_load(p_doctor_id INTEGER, p_date DATE)
RETURNS INTEGER
LANGUAGE sql STABLE AS $$
    SELECT COUNT(*)::INTEGER FROM appointments
    WHERE doctor_id = p_doctor_id AND appointment_date = p_date AND status <> 'Cancelled';
$$;

-- ------------------------------------------------------------
-- Function 3 (set-returning): a doctor's clinic slots for one day and
-- whether each is still bookable. Clinic hours: 09:00-12:30 and
-- 14:00-16:30 on the half hour. Feeds the live slot picker and
-- sp_book_appointment's slot check.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION fn_free_slots(p_doctor_id INTEGER, p_date DATE)
RETURNS TABLE (slot_time TIME, is_free BOOLEAN)
LANGUAGE sql STABLE AS $$
    SELECT s.slot_time,
           NOT EXISTS (SELECT 1 FROM appointments a
                       WHERE a.doctor_id = p_doctor_id AND a.appointment_date = p_date
                         AND a.appointment_time = s.slot_time AND a.status <> 'Cancelled')
           AND (p_date > CURRENT_DATE OR (p_date = CURRENT_DATE AND s.slot_time > LOCALTIME))
           AND EXTRACT(DOW FROM p_date) <> 0
    FROM (SELECT (TIME '09:00' + n * INTERVAL '30 minutes')::TIME AS slot_time
          FROM generate_series(0, 15) AS n) s
    WHERE s.slot_time NOT IN (TIME '13:00', TIME '13:30')
    ORDER BY s.slot_time;
$$;

-- ------------------------------------------------------------
-- Procedure 1: book an appointment with validation.
-- Rejects past dates, inactive doctors and slot clashes with a
-- readable message; the app shows that message to the patient.
-- uq_doctor_slot (schema.sql) is the backstop for concurrent bookings.
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_book_appointment(
    p_patient_id INTEGER,
    p_doctor_id INTEGER,
    p_date DATE,
    p_time TIME,
    p_reason VARCHAR
)
LANGUAGE plpgsql AS $$
BEGIN
    IF p_date < CURRENT_DATE THEN
        RAISE EXCEPTION 'Appointment date cannot be in the past.';
    END IF;

    IF EXTRACT(DOW FROM p_date) = 0 THEN
        RAISE EXCEPTION 'The clinic is closed on Sundays.';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM fn_free_slots(p_doctor_id, p_date) WHERE slot_time = p_time) THEN
        RAISE EXCEPTION 'Please choose a clinic slot: 09:00-12:30 or 14:00-16:30, on the hour or half hour.';
    END IF;

    IF p_date = CURRENT_DATE AND p_time <= LOCALTIME THEN
        RAISE EXCEPTION 'That time has already passed today.';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM doctors d JOIN users u ON u.user_id = d.user_id
        WHERE d.doctor_id = p_doctor_id AND u.is_active
    ) THEN
        RAISE EXCEPTION 'The selected doctor is not available.';
    END IF;

    IF EXISTS (
        SELECT 1 FROM appointments
        WHERE doctor_id = p_doctor_id AND appointment_date = p_date
          AND appointment_time = p_time AND status <> 'Cancelled'
    ) THEN
        RAISE EXCEPTION 'This doctor is already booked at % on %. Please choose another slot.',
            to_char(p_time, 'HH24:MI'), to_char(p_date, 'DD Mon YYYY');
    END IF;

    INSERT INTO appointments (patient_id, doctor_id, appointment_date, appointment_time, reason)
    VALUES (p_patient_id, p_doctor_id, p_date, p_time, p_reason);
END;
$$;

-- ------------------------------------------------------------
-- Procedure 2: complete a visit atomically -- mark the appointment
-- Completed AND write the medical record (with optional vitals).
-- Both happen in the caller's transaction, so either both persist
-- or neither does.
-- ------------------------------------------------------------
DROP PROCEDURE IF EXISTS sp_complete_visit(INTEGER, INTEGER, TEXT, TEXT, TEXT);  -- old 5-argument version
CREATE OR REPLACE PROCEDURE sp_complete_visit(
    p_appointment_id INTEGER,
    p_doctor_id INTEGER,
    p_diagnosis TEXT,
    p_prescription TEXT,
    p_notes TEXT,
    p_bp_systolic SMALLINT DEFAULT NULL,
    p_bp_diastolic SMALLINT DEFAULT NULL,
    p_heart_rate SMALLINT DEFAULT NULL,
    p_temperature_c NUMERIC DEFAULT NULL,
    p_weight_kg NUMERIC DEFAULT NULL
)
LANGUAGE plpgsql AS $$
DECLARE
    v_patient_id INTEGER;
BEGIN
    SELECT patient_id INTO v_patient_id FROM appointments
    WHERE appointment_id = p_appointment_id AND doctor_id = p_doctor_id AND status <> 'Cancelled';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Appointment % was not found or has been cancelled.', p_appointment_id;
    END IF;

    UPDATE appointments SET status = 'Completed' WHERE appointment_id = p_appointment_id;

    INSERT INTO medical_records (patient_id, doctor_id, appointment_id, diagnosis, prescription, notes,
                                 bp_systolic, bp_diastolic, heart_rate, temperature_c, weight_kg)
    VALUES (v_patient_id, p_doctor_id, p_appointment_id, p_diagnosis, p_prescription, p_notes,
            p_bp_systolic, p_bp_diastolic, p_heart_rate, p_temperature_c, p_weight_kg);
END;
$$;

-- ------------------------------------------------------------
-- Procedure 3: reschedule a patient's booking. Cancels the old slot
-- and books the new one through sp_book_appointment (same rules).
-- If the new slot is rejected, the cancellation is rolled back too.
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_reschedule_appointment(
    p_appointment_id INTEGER,
    p_patient_id INTEGER,
    p_new_date DATE,
    p_new_time TIME
)
LANGUAGE plpgsql AS $$
DECLARE
    v_doctor_id INTEGER;
    v_reason VARCHAR;
BEGIN
    SELECT doctor_id, reason INTO v_doctor_id, v_reason FROM appointments
    WHERE appointment_id = p_appointment_id AND patient_id = p_patient_id AND status = 'Scheduled';

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Only your own scheduled appointments can be rescheduled.';
    END IF;

    UPDATE appointments SET status = 'Cancelled' WHERE appointment_id = p_appointment_id;
    CALL sp_book_appointment(p_patient_id, v_doctor_id, p_new_date, p_new_time, v_reason);
END;
$$;

-- ------------------------------------------------------------
-- Trigger 2: audit every change to medical records
-- (health data must be traceable). Writes to audit_log.
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION log_medical_record_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO audit_log (table_name, operation, record_id, details)
        VALUES ('medical_records', TG_OP, OLD.record_id,
                'Deleted record of patient ' || OLD.patient_id);
        RETURN OLD;
    END IF;

    INSERT INTO audit_log (table_name, operation, record_id, details)
    VALUES ('medical_records', TG_OP, NEW.record_id,
            'Patient ' || NEW.patient_id || ', doctor ' || NEW.doctor_id || ': ' || LEFT(NEW.diagnosis, 60));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_medical_record_audit ON medical_records;
CREATE TRIGGER trg_medical_record_audit
AFTER INSERT OR UPDATE OR DELETE ON medical_records
FOR EACH ROW EXECUTE FUNCTION log_medical_record_change();
