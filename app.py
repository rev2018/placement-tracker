import sqlite3
import csv
from io import StringIO
from datetime import datetime

from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "replace-this-with-a-strong-secret-key"  # change before deploying
DB_NAME = "placement_tracker.db"

STATUSES = ["Applied", "Test", "Interview", "Selected", "Rejected"]


# ---------------- DB Helpers ----------------
def get_db():
    conn = sqlite3.connect(DB_NAME)
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
            updated_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()


# ---------------- Auth Helpers ----------------
def login_required():
    if "user_id" not in session:
        flash("Please login first.", "warning")
        return False
    return True


# ---------------- Routes ----------------
@app.route("/")
def home():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not full_name or not email or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("signup"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("signup"))

        pw_hash = generate_password_hash(password)

        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO users (full_name, email, password_hash, created_at)
                VALUES (?, ?, ?, ?)
            """, (full_name, email, pw_hash, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            flash("Account created! Please login.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email already registered. Try logging in.", "warning")
            return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "danger")
            return redirect(url_for("login"))

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

        flash("Invalid credentials. Try again.", "danger")
        return redirect(url_for("login"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(url_for("login"))

    user_id = session["user_id"]
    search = request.args.get("search", "").strip()
    status_filter = request.args.get("status", "").strip()

    conn = get_db()
    cur = conn.cursor()

    query = "SELECT * FROM applications WHERE user_id = ?"
    params = [user_id]

    if search:
        query += " AND (company_name LIKE ? OR role LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%"])

    if status_filter and status_filter in STATUSES:
        query += " AND status = ?"
        params.append(status_filter)

    query += " ORDER BY updated_at DESC"
    cur.execute(query, params)
    apps = cur.fetchall()

    # Counts
    cur.execute("SELECT status, COUNT(*) as count FROM applications WHERE user_id = ? GROUP BY status", (user_id,))
    counts_rows = cur.fetchall()
    counts = {s: 0 for s in STATUSES}
    for row in counts_rows:
        counts[row["status"]] = row["count"]

    total = sum(counts.values())
    selected = counts.get("Selected", 0)

    conn.close()

    return render_template(
        "dashboard.html",
        applications=apps,
        statuses=STATUSES,
        counts=counts,
        total=total,
        selected=selected,
        search=search,
        status_filter=status_filter
    )


@app.route("/application/new", methods=["GET", "POST"])
def new_application():
    if not login_required():
        return redirect(url_for("login"))

    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        role = request.form.get("role", "").strip()
        status = request.form.get("status", "").strip()
        applied_date = request.form.get("applied_date", "").strip()
        next_round_date = request.form.get("next_round_date", "").strip()
        notes = request.form.get("notes", "").strip()
        resume_link = request.form.get("resume_link", "").strip()

        if not company_name or not role or not applied_date:
            flash("Company name, role and applied date are required.", "danger")
            return redirect(url_for("new_application"))

        if status not in STATUSES:
            status = "Applied"

        now = datetime.now().isoformat()

        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO applications
            (user_id, company_name, role, status, applied_date, next_round_date, notes, resume_link, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (session["user_id"], company_name, role, status, applied_date, next_round_date or None, notes, resume_link, now, now))
        conn.commit()
        conn.close()

        flash("Application added successfully!", "success")
        return redirect(url_for("dashboard"))

    return render_template("application_form.html", mode="new", statuses=STATUSES, app_data=None)


@app.route("/application/<int:app_id>/edit", methods=["GET", "POST"])
def edit_application(app_id):
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM applications WHERE id = ? AND user_id = ?", (app_id, session["user_id"]))
    app_row = cur.fetchone()

    if not app_row:
        conn.close()
        flash("Application not found.", "danger")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        company_name = request.form.get("company_name", "").strip()
        role = request.form.get("role", "").strip()
        status = request.form.get("status", "").strip()
        applied_date = request.form.get("applied_date", "").strip()
        next_round_date = request.form.get("next_round_date", "").strip()
        notes = request.form.get("notes", "").strip()
        resume_link = request.form.get("resume_link", "").strip()

        if not company_name or not role or not applied_date:
            flash("Company name, role and applied date are required.", "danger")
            return redirect(url_for("edit_application", app_id=app_id))

        if status not in STATUSES:
            status = "Applied"

        cur.execute("""
            UPDATE applications
            SET company_name = ?, role = ?, status = ?, applied_date = ?, next_round_date = ?, notes = ?, resume_link = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
        """, (company_name, role, status, applied_date, next_round_date or None, notes, resume_link, datetime.now().isoformat(), app_id, session["user_id"]))
        conn.commit()
        conn.close()

        flash("Application updated!", "success")
        return redirect(url_for("dashboard"))

    conn.close()
    return render_template("application_form.html", mode="edit", statuses=STATUSES, app_data=app_row)


@app.route("/application/<int:app_id>/delete", methods=["POST"])
def delete_application(app_id):
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM applications WHERE id = ? AND user_id = ?", (app_id, session["user_id"]))
    conn.commit()
    conn.close()

    flash("Application deleted.", "info")
    return redirect(url_for("dashboard"))


@app.route("/export")
def export_csv():
    if not login_required():
        return redirect(url_for("login"))

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT company_name, role, status, applied_date, next_round_date, notes, resume_link
        FROM applications
        WHERE user_id = ?
        ORDER BY updated_at DESC
    """, (session["user_id"],))
    rows = cur.fetchall()
    conn.close()

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Company Name", "Role", "Status", "Applied Date", "Next Round Date", "Notes", "Resume Link"])

    for r in rows:
        writer.writerow([r["company_name"], r["role"], r["status"], r["applied_date"], r["next_round_date"] or "", r["notes"] or "", r["resume_link"] or ""])

    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=placement_applications.csv"
    response.headers["Content-Type"] = "text/csv"
    return response


# ---------------- Main ----------------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
