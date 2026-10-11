from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db import execute, query_one

auth_bp = Blueprint("auth", __name__)

ROLE_HOME = {
    "patient": "patient.dashboard",
    "doctor": "doctor.dashboard",
    "lab_assistant": "lab.dashboard",
    "admin": "admin.dashboard",
}

PROFILE_TABLE = {
    "patient": ("patients", "patient_id"),
    "doctor": ("doctors", "doctor_id"),
    "lab_assistant": ("lab_assistants", "lab_assistant_id"),
    "admin": ("admins", "admin_id"),
}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "warning")
                return redirect(url_for("auth.login"))
            if session.get("role") not in roles:
                flash("You do not have access to that page.", "danger")
                return redirect(url_for(ROLE_HOME.get(session.get("role"), "auth.login")))
            return view(*args, **kwargs)

        return wrapped

    return decorator


@auth_bp.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for(ROLE_HOME[session["role"]]))
    stats = query_one(
        """SELECT (SELECT COUNT(*) FROM patients) AS patients, (SELECT COUNT(*) FROM doctors) AS doctors,
                  (SELECT COUNT(*) FROM departments) AS departments,
                  (SELECT COUNT(*) FROM appointments WHERE status = 'Completed') AS visits"""
    )
    return render_template("index.html", stats=stats)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for(ROLE_HOME[session["role"]]))

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form["role"]

        user = query_one(
            "SELECT * FROM users WHERE username = %s AND role = %s AND is_active = TRUE",
            (username, role),
        )

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid username, password, or role.", "danger")
            return render_template("login.html")

        table, id_col = PROFILE_TABLE[role]
        profile = query_one(
            f"SELECT {id_col} AS profile_id, full_name FROM {table} WHERE user_id = %s",
            (user["user_id"],),
        )

        session.clear()
        session["user_id"] = user["user_id"]
        session["username"] = user["username"]
        session["role"] = user["role"]
        session["profile_id"] = profile["profile_id"]
        session["full_name"] = profile["full_name"]

        flash(f"Welcome back, {profile['full_name']}!", "success")
        return redirect(url_for(ROLE_HOME[role]))

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Self-service registration -- patients only. Staff accounts are created by Admin."""
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip()
        password = request.form["password"]
        full_name = request.form["full_name"].strip()
        dob = request.form["dob"]
        gender = request.form["gender"]
        blood_group = request.form.get("blood_group", "")
        phone = request.form.get("phone", "")
        address = request.form.get("address", "")
        emergency_contact = request.form.get("emergency_contact", "")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("register.html")

        existing = query_one(
            "SELECT user_id FROM users WHERE username = %s OR email = %s", (username, email)
        )
        if existing:
            flash("That username or email is already registered.", "danger")
            return render_template("register.html")

        user = execute(
            """INSERT INTO users (username, email, password_hash, role)
               VALUES (%s, %s, %s, 'patient') RETURNING user_id""",
            (username, email, generate_password_hash(password)),
        )
        execute(
            """INSERT INTO patients
               (user_id, full_name, dob, gender, blood_group, phone, address, emergency_contact)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                user["user_id"],
                full_name,
                dob,
                gender,
                blood_group,
                phone,
                address,
                emergency_contact,
            ),
        )

        flash("Registration successful! Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@auth_bp.route("/account/password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        user = query_one("SELECT password_hash FROM users WHERE user_id = %s", (session["user_id"],))
        new = request.form["new_password"]
        if not check_password_hash(user["password_hash"], request.form["current_password"]):
            flash("Your current password is incorrect.", "danger")
        elif len(new) < 6:
            flash("The new password must be at least 6 characters.", "danger")
        elif new != request.form["confirm_password"]:
            flash("The new passwords do not match.", "danger")
        else:
            execute("UPDATE users SET password_hash = %s WHERE user_id = %s", (generate_password_hash(new), session["user_id"]))
            flash("Password updated.", "success")
            return redirect(url_for(ROLE_HOME[session["role"]]))
    return render_template("account_password.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.index"))
