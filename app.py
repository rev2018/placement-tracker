import sqlite3
import csv
from io import StringIO
from datetime import datetime

from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, session, make_response
)
from werkzeug.security import generate_password_hash, check_password_hash


# ---------------- App Setup ----------------
app = Flask(__name__)
app.secret_key = "replace-this-with-a-strong-secret-key"

# Render-safe writable DB
DB_NAME = "/tmp/placement_tracker.db"

STATUSES = ["Applied", "Test", "Interview", "Selected", "Rejected"]


# ---------------- DB Helpers ----------------
def get_db():
    conn = sqlite3.connect(DB_NAME, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # ❌ NO FOREIGN KEY (critical fix)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            company_name TEXT NOT NULL,
            role TEXT NOT NULL,
            status TEXT NOT NULL,
            applied_date TEXT NOT NULL,
            next_round_date TEXT,
            notes TEXT,
            resume_link TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# Initialize DB once
@app.before_request
def ensure_db():
    if not getattr(app, "_db_ready", False):
        init_db()
        app._db_ready = True


# ---------------- Auth Helper ----------------
def login_required():
    if "user_id" not in session:
        flash("Please login first.", "warning")
        return False
    return True


# ---------------- Routes ----------------
@app.route("/")
def home():
    return redirect(url_for("dashboard")) if "user_id" in session else redirect(url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        try:
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            if not full_name or not email or not password:
                flash("All fields are required.", "danger")
                return redirect(url_for("signup"))

            pw_hash = generate_password_hash(password)

            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (full_name, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
                (full_name, email, pw_hash, datetime.now().isoformat())
            )
            conn.commit()
            conn.close()

            flash("Account created! Please login.", "success")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("Email already registered.", "warning")
        except Exception as e:
            print("SIGNUP ERROR:", e)
            flash("Signup failed.", "danger")

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            conn = get_db()
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE email = ?", (email,))
            user = cur.fetchone()
            conn.close()

            if user and check_password_hash(user["password_hash"], password):
                session["user_id"] = user["id"]
                session["full_name"] = user["full_name"]
                flash("Logged in successfully!", "success")
                return redirect(url_for("dashboard"))

            flash("Invalid credentials.", "danger")

        except Exception as e:
            print("LOGIN ERROR:", e)
            flash("Login failed.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM applications WHERE user_id = ?", (session["user_id"],))
    apps = cur.fetchall()
    conn.close()

    return render_template("dashboard.html", applications=apps, statuses=STATUSES)


@app.route("/application/new", methods=["GET", "POST"])
def new_application():
    if not login_required():
        return redirect(url_for("login"))

    if request.method == "POST":
        try:
            now = datetime.now().isoformat()

            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO applications
                (user_id, company_name, role, status, applied_date,
                 next_round_date, notes, resume_link, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session["user_id"],
                request.form.get("company_name"),
                request.form.get("role"),
                request.form.get("status", "Applied"),
                request.form.get("applied_date"),
                request.form.get("next_round_date"),
                request.form.get("notes"),
                request.form.get("resume_link"),
                now,
                now
            ))
            conn.commit()
            conn.close()

            flash("Application added successfully!", "success")
            return redirect(url_for("dashboard"))

        except Exception as e:
            print("APPLICATION ERROR:", e)
            flash("Failed to save application.", "danger")

    return render_template("application_form.html", mode="new", statuses=STATUSES)


@app.route("/export")
def export_csv():
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT company_name, role, status, applied_date,
               next_round_date, notes, resume_link
        FROM applications
        WHERE user_id = ?
    """, (session["user_id"],))
    rows = cur.fetchall()
    conn.close()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Company", "Role", "Status",
        "Applied Date", "Next Round Date",
        "Notes", "Resume Link"
    ])

    for r in rows:
        writer.writerow([
            r["company_name"],
            r["role"],
            r["status"],
            r["applied_date"],
            r["next_round_date"] or "",
            r["notes"] or "",
            r["resume_link"] or ""
        ])

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=applications.csv"
    response.headers["Content-Type"] = "text/csv"
    return response


# ---------------- Main ----------------
if __name__ == "__main__":
    app.run()

