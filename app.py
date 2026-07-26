import traceback

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
        return {"current_role": session.get("role"), "current_name": session.get("full_name")}

    @app.route("/_debug_db")
    def _debug_db():
        # TEMPORARY diagnostic route -- remove once the deployment is confirmed healthy.
        try:
            row = db.query_one("SELECT COUNT(*) AS n FROM users")
            return {"ok": True, "user_count": row["n"]}
        except Exception as e:
            return {"ok": False, "error": repr(e), "trace": traceback.format_exc()}, 500

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
