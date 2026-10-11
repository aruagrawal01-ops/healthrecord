from flask import Flask, render_template, session

import db
from admin_routes import admin_bp
from auth import auth_bp
from config import Config
from doctor_routes import doctor_bp
from lab_routes import lab_bp
from patient_routes import patient_bp


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(patient_bp)
    app.register_blueprint(doctor_bp)
    app.register_blueprint(lab_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def inject_session():
        role = session.get("role")
        ctx = {"current_role": role, "current_name": session.get("full_name"), "notices": [], "nav_counts": {}}
        if role:
            ctx["notices"] = db.query_all(
                """SELECT title, body, is_pinned FROM announcements
                   WHERE audience IN ('all', %s) ORDER BY is_pinned DESC, created_at DESC LIMIT 5""",
                (role,),
            )
            if role == "lab_assistant":
                ctx["nav_counts"]["pending_tests"] = db.query_one("SELECT COUNT(*) AS n FROM lab_tests WHERE status = 'Pending'")["n"]
            elif role == "doctor":
                ctx["nav_counts"]["today"] = db.query_one(
                    "SELECT fn_doctor_load(%s, CURRENT_DATE) AS n", (session["profile_id"],)
                )["n"]
        return ctx

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
