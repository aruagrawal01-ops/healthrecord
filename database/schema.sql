-- ============================================================
-- Patient Health Record Management System
-- Database Schema (PostgreSQL)
-- Normalized to BCNF
-- Run order: schema.sql -> advanced_features.sql -> seed_data.sql -> bulk_demo_data.sql
-- ============================================================

DROP TABLE IF EXISTS announcements CASCADE;
DROP TABLE IF EXISTS audit_log CASCADE;
DROP TABLE IF EXISTS lab_reports CASCADE;
DROP TABLE IF EXISTS lab_tests CASCADE;
DROP TABLE IF EXISTS medical_records CASCADE;
DROP TABLE IF EXISTS appointments CASCADE;
DROP TABLE IF EXISTS admins CASCADE;
DROP TABLE IF EXISTS lab_assistants CASCADE;
DROP TABLE IF EXISTS doctors CASCADE;
DROP TABLE IF EXISTS patients CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS departments CASCADE;

-- ------------------------------------------------------------
-- Departments (e.g. Cardiology, Orthopedics)
-- ------------------------------------------------------------
CREATE TABLE departments (
    department_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

-- ------------------------------------------------------------
-- Users: one row per login account, shared across all 4 roles
-- ------------------------------------------------------------
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(120) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('patient', 'doctor', 'lab_assistant', 'admin')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- Role-specific profile tables (1-to-1 with users)
-- ------------------------------------------------------------
CREATE TABLE patients (
    patient_id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    full_name VARCHAR(100) NOT NULL,
    dob DATE NOT NULL,
    gender VARCHAR(10) CHECK (gender IN ('Male', 'Female', 'Other')),
    blood_group VARCHAR(5),
    phone VARCHAR(15),
    address TEXT,
    emergency_contact VARCHAR(15)
);

CREATE TABLE doctors (
    doctor_id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    full_name VARCHAR(100) NOT NULL,
    specialization VARCHAR(100),
    qualification VARCHAR(150),
    department_id INTEGER REFERENCES departments(department_id) ON DELETE SET NULL,
    phone VARCHAR(15)
);

CREATE TABLE lab_assistants (
    lab_assistant_id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    full_name VARCHAR(100) NOT NULL,
    phone VARCHAR(15)
);

CREATE TABLE admins (
    admin_id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    full_name VARCHAR(100) NOT NULL
);

-- ------------------------------------------------------------
-- Appointments: patient books time with a doctor
-- ------------------------------------------------------------
CREATE TABLE appointments (
    appointment_id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    doctor_id INTEGER NOT NULL REFERENCES doctors(doctor_id) ON DELETE CASCADE,
    appointment_date DATE NOT NULL,
    appointment_time TIME NOT NULL,
    reason VARCHAR(255),
    status VARCHAR(20) NOT NULL DEFAULT 'Scheduled'
        CHECK (status IN ('Scheduled', 'Completed', 'Cancelled')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- Medical records: diagnosis + prescription written by a doctor
-- ------------------------------------------------------------
CREATE TABLE medical_records (
    record_id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    doctor_id INTEGER NOT NULL REFERENCES doctors(doctor_id) ON DELETE CASCADE,
    appointment_id INTEGER REFERENCES appointments(appointment_id) ON DELETE SET NULL,
    diagnosis TEXT NOT NULL,
    prescription TEXT,
    notes TEXT,
    -- Vitals taken at the visit (optional); ranges reject typos like 1200 bpm
    bp_systolic SMALLINT CHECK (bp_systolic BETWEEN 60 AND 250),
    bp_diastolic SMALLINT CHECK (bp_diastolic BETWEEN 30 AND 150),
    heart_rate SMALLINT CHECK (heart_rate BETWEEN 30 AND 220),
    temperature_c NUMERIC(4,1) CHECK (temperature_c BETWEEN 30 AND 45),
    weight_kg NUMERIC(5,1) CHECK (weight_kg BETWEEN 1 AND 300),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- Lab tests: doctor requests a test for a patient
-- ------------------------------------------------------------
CREATE TABLE lab_tests (
    lab_test_id SERIAL PRIMARY KEY,
    patient_id INTEGER NOT NULL REFERENCES patients(patient_id) ON DELETE CASCADE,
    doctor_id INTEGER NOT NULL REFERENCES doctors(doctor_id) ON DELETE CASCADE,
    test_name VARCHAR(150) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Pending'
        CHECK (status IN ('Pending', 'Completed')),
    requested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- Lab reports: lab assistant uploads result for a lab test.
-- File bytes stored directly in the DB (BYTEA) so the app has
-- no dependency on server-local disk storage -- required for
-- serverless hosting (Vercel) where the filesystem is ephemeral.
-- ------------------------------------------------------------
CREATE TABLE lab_reports (
    report_id SERIAL PRIMARY KEY,
    lab_test_id INTEGER UNIQUE NOT NULL REFERENCES lab_tests(lab_test_id) ON DELETE CASCADE,
    lab_assistant_id INTEGER NOT NULL REFERENCES lab_assistants(lab_assistant_id) ON DELETE CASCADE,
    result_summary TEXT NOT NULL,
    file_name VARCHAR(255),
    file_type VARCHAR(100),
    file_data BYTEA,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- Indexes for common lookups
-- ------------------------------------------------------------
CREATE INDEX idx_appointments_patient ON appointments(patient_id);
CREATE INDEX idx_appointments_doctor ON appointments(doctor_id);
CREATE INDEX idx_records_patient ON medical_records(patient_id);
CREATE INDEX idx_labtests_patient ON lab_tests(patient_id);
CREATE INDEX idx_labtests_status ON lab_tests(status);
CREATE INDEX idx_appointments_date ON appointments(appointment_date);

-- Appointment clash rule: a doctor cannot have two live bookings in the
-- same slot. Partial, so a Cancelled slot can be booked again.
CREATE UNIQUE INDEX uq_doctor_slot ON appointments(doctor_id, appointment_date, appointment_time)
    WHERE status <> 'Cancelled';

-- ------------------------------------------------------------
-- Audit log: written only by trg_medical_record_audit
-- (see advanced_features.sql). Support table, outside the core model.
-- ------------------------------------------------------------
CREATE TABLE audit_log (
    log_id SERIAL PRIMARY KEY,
    table_name VARCHAR(50) NOT NULL,
    operation VARCHAR(10) NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    record_id INTEGER NOT NULL,
    details TEXT,
    changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- Announcements: notices the admin posts to one role or everyone
-- ------------------------------------------------------------
CREATE TABLE announcements (
    announcement_id SERIAL PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    body TEXT NOT NULL,
    audience VARCHAR(20) NOT NULL DEFAULT 'all'
        CHECK (audience IN ('all', 'patient', 'doctor', 'lab_assistant')),
    is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
    created_by INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ------------------------------------------------------------
-- Trigger: auto-mark a lab test Completed as soon as its report
-- is uploaded (keeps status consistent without extra app logic)
-- ------------------------------------------------------------
CREATE OR REPLACE FUNCTION mark_lab_test_completed()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE lab_tests SET status = 'Completed' WHERE lab_test_id = NEW.lab_test_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_lab_report_insert
AFTER INSERT ON lab_reports
FOR EACH ROW EXECUTE FUNCTION mark_lab_test_completed();

-- ------------------------------------------------------------
-- Views used by the application (demonstrate joins / reporting)
-- ------------------------------------------------------------

-- Full patient history: appointments + diagnosis + prescriptions
CREATE OR REPLACE VIEW view_patient_history AS
SELECT
    p.patient_id,
    p.full_name AS patient_name,
    d.full_name AS doctor_name,
    mr.diagnosis,
    mr.prescription,
    mr.notes,
    mr.created_at AS record_date
FROM medical_records mr
JOIN patients p ON mr.patient_id = p.patient_id
JOIN doctors d ON mr.doctor_id = d.doctor_id
ORDER BY mr.created_at DESC;

-- Doctor's appointment schedule with patient contact info
CREATE OR REPLACE VIEW view_doctor_schedule AS
SELECT
    a.appointment_id,
    a.doctor_id,
    d.full_name AS doctor_name,
    p.patient_id,
    p.full_name AS patient_name,
    p.phone AS patient_phone,
    a.appointment_date,
    a.appointment_time,
    a.reason,
    a.status
FROM appointments a
JOIN patients p ON a.patient_id = p.patient_id
JOIN doctors d ON a.doctor_id = d.doctor_id;

-- Pending lab tests queue for lab assistants
CREATE OR REPLACE VIEW view_pending_lab_tests AS
SELECT
    lt.lab_test_id,
    lt.test_name,
    lt.requested_at,
    p.patient_id,
    p.full_name AS patient_name,
    doc.full_name AS requested_by
FROM lab_tests lt
JOIN patients p ON lt.patient_id = p.patient_id
JOIN doctors doc ON lt.doctor_id = doc.doctor_id
WHERE lt.status = 'Pending'
ORDER BY lt.requested_at ASC;

-- Admin dashboard summary counts
CREATE OR REPLACE VIEW view_admin_stats AS
SELECT
    (SELECT COUNT(*) FROM patients) AS total_patients,
    (SELECT COUNT(*) FROM doctors) AS total_doctors,
    (SELECT COUNT(*) FROM lab_assistants) AS total_lab_assistants,
    (SELECT COUNT(*) FROM appointments WHERE appointment_date = CURRENT_DATE) AS todays_appointments,
    (SELECT COUNT(*) FROM lab_tests WHERE status = 'Pending') AS pending_lab_tests;

-- Per-doctor workload and outcomes (admin reports page)
CREATE OR REPLACE VIEW view_doctor_performance AS
SELECT
    d.doctor_id,
    d.full_name AS doctor_name,
    dep.name AS department,
    COUNT(a.appointment_id) AS total_appointments,
    COUNT(*) FILTER (WHERE a.status = 'Completed') AS completed,
    COUNT(*) FILTER (WHERE a.status = 'Cancelled') AS cancelled,
    COUNT(*) FILTER (WHERE a.status = 'Scheduled') AS upcoming,
    COUNT(DISTINCT a.patient_id) AS patients_seen,
    ROUND(100.0 * COUNT(*) FILTER (WHERE a.status = 'Completed')
          / NULLIF(COUNT(*) FILTER (WHERE a.status <> 'Scheduled'), 0), 1) AS completion_rate
FROM doctors d
LEFT JOIN departments dep ON d.department_id = dep.department_id
LEFT JOIN appointments a ON a.doctor_id = d.doctor_id
GROUP BY d.doctor_id, d.full_name, dep.name;

-- Per-department totals (admin reports page)
CREATE OR REPLACE VIEW view_department_stats AS
SELECT
    dep.department_id,
    dep.name AS department,
    COUNT(DISTINCT d.doctor_id) AS doctors,
    COUNT(a.appointment_id) AS appointments,
    COUNT(*) FILTER (WHERE a.status = 'Completed') AS completed,
    COUNT(DISTINCT a.patient_id) AS patients
FROM departments dep
LEFT JOIN doctors d ON d.department_id = dep.department_id
LEFT JOIN appointments a ON a.doctor_id = d.doctor_id
GROUP BY dep.department_id, dep.name;
