@app.route("/application/new", methods=["GET", "POST"])
def new_application():
    if not login_required():
        return redirect(url_for("login"))

    if request.method == "POST":
        try:
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
            """, (
                session["user_id"],
                company_name,
                role,
                status,
                applied_date,
                next_round_date or None,
                notes,
                resume_link,
                now,
                now
            ))
            conn.commit()
            conn.close()

            flash("Application added successfully!", "success")
            return redirect(url_for("dashboard"))

        except Exception as e:
            print("NEW APPLICATION ERROR:", e)
            flash("Something went wrong while saving. Please try again.", "danger")
            return redirect(url_for("new_application"))

    return render_template(
        "application_form.html",
        mode="new",
        statuses=STATUSES,
        app_data=None
    )

