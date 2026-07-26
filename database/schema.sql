-- ============================================================
-- Patient Health Record Management System
-- Database Schema (PostgreSQL)
-- Normalized to 3NF
-- ============================================================

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
