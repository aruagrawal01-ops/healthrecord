-- ============================================================
-- Advanced database features (Review 2)
-- Run after schema.sql. Safe to re-run.
--   Procedures: sp_book_appointment, sp_complete_visit
--   Functions:  fn_patient_age, fn_doctor_load
--   Triggers:   trg_lab_report_insert (schema.sql), trg_medical_record_audit
--   Views:      4 views in schema.sql
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
-- Completed AND write the medical record. Both happen in the
-- caller's transaction, so either both persist or neither does.
-- ------------------------------------------------------------
CREATE OR REPLACE PROCEDURE sp_complete_visit(
    p_appointment_id INTEGER,
    p_doctor_id INTEGER,
    p_diagnosis TEXT,
    p_prescription TEXT,
    p_notes TEXT
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

    INSERT INTO medical_records (patient_id, doctor_id, appointment_id, diagnosis, prescription, notes)
    VALUES (v_patient_id, p_doctor_id, p_appointment_id, p_diagnosis, p_prescription, p_notes);
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
