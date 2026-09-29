from flask import (
    Flask, render_template, request, redirect, flash, jsonify,
    send_from_directory, session, url_for
)
import sqlite3
import smtplib
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path
from email.message import EmailMessage
from functools import wraps
from getpass import getpass
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = "minor_project_secret_key_2026"
DATABASE = Path(__file__).resolve().parent / "donors.db"

# Fill these ONLY if you want real password-reset emails.
EMAIL_SENDER = "YOUR_GMAIL@gmail.com"
EMAIL_APP_PASSWORD = "YOUR_GMAIL_APP_PASSWORD"

MIN_AGE, MAX_AGE = 18, 65
MIN_WEIGHT = 45.0
MIN_HEMOGLOBIN = 12.5
MIN_DAYS_BETWEEN_DONATIONS = 90


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def calculate_age(dob):
    d = date.fromisoformat(dob)
    t = date.today()
    age = t.year - d.year
    if (t.month, t.day) < (d.month, d.day):
        age -= 1
    return age


def calculate_bmi(height, weight):
    bmi = round(weight / ((height / 100) ** 2), 2)
    if bmi < 18.5:
        status = "Underweight"
    elif bmi < 25:
        status = "Normal"
    elif bmi < 30:
        status = "Overweight"
    else:
        status = "Obesity"
    return bmi, status


def check_eligibility(age, weight, last_donation, hemoglobin, pallor):
    if age < MIN_AGE:
        return False, "Age is below the prototype minimum of 18 years."
    if weight < MIN_WEIGHT:
        return False, "Weight is below the prototype minimum of 45 kg."
    if hemoglobin < MIN_HEMOGLOBIN:
        return False, "Hemoglobin is below the prototype threshold of 12.5 g/dL."
    if pallor != "No":
        return False, "Pallor screening did not pass the prototype rule."
    if last_donation:
        try:
            last = date.fromisoformat(last_donation)
        except ValueError:
            return False, "Last donation date is invalid."
        if last > date.today():
            return False, "Last donation date cannot be in the future."
        if (date.today() - last).days < MIN_DAYS_BETWEEN_DONATIONS:
            return False, "At least 90 days are required since the last donation under this prototype rule."
    return True, "Passed preliminary screening."


def setup_database():
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS donors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            gender TEXT,
            phone TEXT NOT NULL,
            email TEXT,
            location TEXT NOT NULL,
            age INTEGER NOT NULL,
            date_of_birth TEXT,
            password_hash TEXT,
            height REAL,
            weight REAL NOT NULL,
            bmi REAL,
            bmi_status TEXT,
            last_donation_date TEXT,
            screening_date TEXT,
            hemoglobin REAL,
            pallor_observed TEXT,
            consent INTEGER DEFAULT 0,
            is_eligible INTEGER DEFAULT 0,
            available INTEGER DEFAULT 1,
            reset_code TEXT,
            reset_code_expiry TEXT
        )
    """)

    existing = {
        r["name"]
        for r in conn.execute("PRAGMA table_info(donors)").fetchall()
    }

    additions = {
        "gender": "TEXT",
        "date_of_birth": "TEXT",
        "password_hash": "TEXT",
        "height": "REAL",
        "bmi": "REAL",
        "bmi_status": "TEXT",
        "screening_date": "TEXT",
        "hemoglobin": "REAL",
        "pallor_observed": "TEXT",
        "consent": "INTEGER DEFAULT 0",
        "available": "INTEGER DEFAULT 1",
        "reset_code": "TEXT",
        "reset_code_expiry": "TEXT"
    }

    for name, definition in additions.items():
        if name not in existing:
            conn.execute(
                f"ALTER TABLE donors ADD COLUMN {name} {definition}"
            )

    # Blood request table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blood_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_name TEXT NOT NULL,
            blood_group TEXT NOT NULL,
            units INTEGER NOT NULL DEFAULT 1,
            hospital TEXT NOT NULL,
            location TEXT NOT NULL,
            contact_phone TEXT NOT NULL,
            required_date TEXT NOT NULL,
            notes TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Admin table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def send_reset_email(recipient, code):
    if (
        EMAIL_SENDER == "YOUR_GMAIL@gmail.com"
        or EMAIL_APP_PASSWORD == "YOUR_GMAIL_APP_PASSWORD"
    ):
        raise RuntimeError("Email settings are not configured in app.py")

    msg = EmailMessage()
    msg["Subject"] = "Blood Donor Management System - Password Reset"
    msg["From"], msg["To"] = EMAIL_SENDER, recipient
    msg.set_content(
        f"Your password reset code is: {code}\n\n"
        "This code is valid for 10 minutes."
    )

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_SENDER, EMAIL_APP_PASSWORD)
        smtp.send_message(msg)


# Admin access protection
def admin_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please log in as an admin first.", "warning")
            return redirect(url_for("admin_login"))
        return view_function(*args, **kwargs)
    return wrapped_view


@app.route("/")
def home():
    conn = get_db()
    donor_count = conn.execute(
        "SELECT COUNT(*) FROM donors"
    ).fetchone()[0]

    eligible_count = conn.execute(
        "SELECT COUNT(*) FROM donors WHERE is_eligible=1 AND available=1"
    ).fetchone()[0]

    conn.close()

    return render_template(
        "index.html",
        donor_count=donor_count,
        eligible_count=eligible_count
    )


@app.route("/check-email")
def check_email():
    email = request.args.get("email", "").strip().lower()

    conn = get_db()
    row = conn.execute(
        "SELECT id FROM donors WHERE LOWER(email)=LOWER(?) LIMIT 1",
        (email,)
    ).fetchone()
    conn.close()

    return jsonify({"exists": row is not None})


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    try:
        name = request.form.get("name", "").strip()
        bg = request.form.get("blood_group", "").strip()
        gender = request.form.get("gender", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()
        location = request.form.get("location", "").strip()
        dob = request.form.get("date_of_birth", "").strip()

        if dob:
            if date.fromisoformat(dob) > date.today():
                flash("Date of birth cannot be in the future.", "danger")
                return render_template("register.html")
            age = calculate_age(dob)
        else:
            age = int(request.form.get("age", "0"))
            dob = None

        height = float(request.form.get("height_cm", "0"))
        weight = float(request.form.get("weight", "0"))
        last = request.form.get("last_donation_date", "").strip()
        hb = float(request.form.get("hemoglobin", "0"))
        pallor = request.form.get("pallor_observed", "").strip()
        consent = request.form.get("consent") == "on"
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not all([name, bg, gender, phone, email, location]):
            flash("Please fill in all required donor details.", "danger")
            return render_template("register.html")

        if not consent:
            flash("Consent is required for registration.", "danger")
            return render_template("register.html")

        if not MIN_AGE <= age <= MAX_AGE:
            flash("Age must be between 18 and 65 for this prototype.", "danger")
            return render_template("register.html")

        if not 100 <= height <= 250 or not 20 <= weight <= 250 or not 0 < hb <= 25:
            flash("Please enter valid height, weight and hemoglobin values.", "danger")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must contain at least 6 characters.", "danger")
            return render_template("register.html")

        if password != confirm:
            flash("Password and Confirm Password do not match.", "danger")
            return render_template("register.html")

        conn = get_db()

        if conn.execute(
            "SELECT id FROM donors WHERE LOWER(email)=LOWER(?) LIMIT 1",
            (email,)
        ).fetchone():
            conn.close()
            flash("This email is already registered.", "danger")
            return render_template("register.html")

        bmi, bmi_status = calculate_bmi(height, weight)
        eligible, reason = check_eligibility(age, weight, last, hb, pallor)

        conn.execute("""
            INSERT INTO donors (
                name, blood_group, gender, phone, email, location,
                age, date_of_birth, password_hash, height, weight,
                bmi, bmi_status, last_donation_date, hemoglobin,
                pallor_observed, consent, is_eligible, available
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name, bg, gender, phone, email, location, age, dob,
            generate_password_hash(password), height, weight, bmi,
            bmi_status, last or None, hb, pallor, int(consent),
            int(eligible), 1
        ))

        conn.commit()

        donor_id = conn.execute(
            "SELECT last_insert_rowid()"
        ).fetchone()[0]

        donor = conn.execute(
            "SELECT * FROM donors WHERE id=?",
            (donor_id,)
        ).fetchone()

        conn.close()

        flash("Registration successful!", "success")
        return render_template("profile.html", donor=donor)

    except (ValueError, TypeError):
        flash("Please enter valid values in all numeric/date fields.", "danger")
        return render_template("register.html")

    except sqlite3.Error as e:
        print("Database error:", e)
        flash("A database error occurred while saving the donor.", "danger")
        return render_template("register.html")


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method == "GET":
        return render_template("profile_login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    if not email or not password:
        flash("Please enter your email and password.", "danger")
        return redirect("/profile")

    conn = get_db()
    donor = conn.execute(
        "SELECT * FROM donors WHERE LOWER(email)=LOWER(?) LIMIT 1",
        (email,)
    ).fetchone()
    conn.close()

    if (
        not donor
        or not donor["password_hash"]
        or not check_password_hash(donor["password_hash"], password)
    ):
        flash("Invalid email or password.", "danger")
        return redirect("/profile")

    return render_template("profile.html", donor=donor)


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "GET":
        try:
            return render_template("forgot_password.html")
        except Exception:
            return (
                '<h2>Forgot Password</h2>'
                '<form method="POST">'
                '<input type="email" name="email" required>'
                '<button>Send Reset Code</button></form>'
            )

    email = request.form.get("email", "").strip().lower()

    conn = get_db()
    donor = conn.execute(
        "SELECT id FROM donors WHERE LOWER(email)=LOWER(?) LIMIT 1",
        (email,)
    ).fetchone()

    if not donor:
        conn.close()
        flash("No donor account was found with this email.", "danger")
        return redirect("/forgot-password")

    code = str(secrets.randbelow(900000) + 100000)
    expiry = datetime.now() + timedelta(minutes=10)

    conn.execute(
        "UPDATE donors SET reset_code=?, reset_code_expiry=? WHERE id=?",
        (code, expiry.isoformat(), donor["id"])
    )
    conn.commit()
    conn.close()

    try:
        send_reset_email(email, code)
    except Exception as e:
        print("Email error:", e)

        conn = get_db()
        conn.execute(
            "UPDATE donors SET reset_code=NULL, reset_code_expiry=NULL WHERE id=?",
            (donor["id"],)
        )
        conn.commit()
        conn.close()

        flash(
            "Password reset email could not be sent. Check the email settings in app.py.",
            "danger"
        )
        return redirect("/forgot-password")

    flash("A password reset code has been sent to your email.", "success")
    return redirect("/reset-password")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if request.method == "GET":
        try:
            return render_template("reset_password.html")
        except Exception:
            return (
                '<h2>Reset Password</h2>'
                '<form method="POST">'
                '<input type="email" name="email" required>'
                '<input name="reset_code" required>'
                '<input type="password" name="new_password" required>'
                '<input type="password" name="confirm_password" required>'
                '<button>Reset Password</button></form>'
            )

    email = request.form.get("email", "").strip().lower()
    code = request.form.get("reset_code", "").strip()
    new = request.form.get("new_password", request.form.get("password", ""))
    confirm = request.form.get("confirm_password", "")

    if len(new) < 6:
        flash("New password must contain at least 6 characters.", "danger")
        return redirect("/reset-password")

    if new != confirm:
        flash("New password and Confirm Password do not match.", "danger")
        return redirect("/reset-password")

    conn = get_db()
    donor = conn.execute(
        "SELECT * FROM donors WHERE LOWER(email)=LOWER(?) LIMIT 1",
        (email,)
    ).fetchone()

    if not donor or not donor["reset_code"] or donor["reset_code"] != code:
        conn.close()
        flash("Invalid email or reset code.", "danger")
        return redirect("/reset-password")

    try:
        expired = datetime.now() > datetime.fromisoformat(
            donor["reset_code_expiry"]
        )
    except (TypeError, ValueError):
        expired = True

    if expired:
        conn.close()
        flash("The password reset code has expired.", "danger")
        return redirect("/reset-password")

    conn.execute(
        "UPDATE donors SET password_hash=?, reset_code=NULL, reset_code_expiry=NULL WHERE id=?",
        (generate_password_hash(new), donor["id"])
    )
    conn.commit()
    conn.close()

    flash("Password reset successfully. You can now log in.", "success")
    return redirect("/profile")


@app.route("/profile/update/<int:donor_id>", methods=["POST"])
def update_profile(donor_id):
    try:
        name = request.form.get("name", "").strip()
        bg = request.form.get("blood_group", "").strip()
        gender = request.form.get("gender", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()
        location = request.form.get("location", "").strip()
        dob = request.form.get("date_of_birth", "").strip()

        if dob:
            if date.fromisoformat(dob) > date.today():
                raise ValueError
            age = calculate_age(dob)
        else:
            age = int(request.form.get("age", "0"))
            dob = None

        height = float(request.form.get("height_cm", "0"))
        weight = float(request.form.get("weight", "0"))
        last = request.form.get("last_donation_date", "").strip()
        hb = float(request.form.get("hemoglobin", "0"))
        pallor = request.form.get("pallor_observed", "").strip()
        consent = request.form.get("consent") == "on"

        if (
            not MIN_AGE <= age <= MAX_AGE
            or not 100 <= height <= 250
            or not 20 <= weight <= 250
            or not 0 < hb <= 25
        ):
            raise ValueError

        bmi, status = calculate_bmi(height, weight)
        eligible, reason = check_eligibility(age, weight, last, hb, pallor)

        conn = get_db()

        if conn.execute(
            "SELECT id FROM donors WHERE LOWER(email)=LOWER(?) AND id!=? LIMIT 1",
            (email, donor_id)
        ).fetchone():
            conn.close()
            flash("This email is already registered to another donor.", "danger")
            return redirect("/profile")

        conn.execute("""
            UPDATE donors SET
                name=?, blood_group=?, gender=?, phone=?, email=?, location=?,
                age=?, date_of_birth=?, height=?, weight=?, bmi=?, bmi_status=?,
                last_donation_date=?, hemoglobin=?, pallor_observed=?,
                consent=?, is_eligible=?
            WHERE id=?
        """, (
            name, bg, gender, phone, email, location, age, dob,
            height, weight, bmi, status, last or None, hb, pallor,
            int(consent), int(eligible), donor_id
        ))

        conn.commit()
        donor = conn.execute(
            "SELECT * FROM donors WHERE id=?",
            (donor_id,)
        ).fetchone()
        conn.close()

        flash(
            f"Profile updated successfully! {reason}",
            "success" if eligible else "warning"
        )
        return render_template("profile.html", donor=donor)

    except (ValueError, TypeError):
        flash("Please enter valid profile values.", "danger")
        return redirect("/profile")


@app.route("/profile/availability/<int:donor_id>", methods=["POST"])
def update_availability(donor_id):
    available = 1 if request.form.get("available") == "1" else 0

    conn = get_db()
    conn.execute(
        "UPDATE donors SET available=? WHERE id=?",
        (available, donor_id)
    )
    conn.commit()
    conn.close()

    flash("Availability status updated.", "success")
    return redirect("/profile")


# SEARCH ROUTE
@app.route("/search")
def search():
    bg = request.args.get("blood_group", "").strip()
    location = request.args.get("location", "").strip()

    conn = get_db()

    query = """
        SELECT id, name, blood_group, location, available
        FROM donors
        WHERE is_eligible=1
    """

    params = []

    if bg:
        query += " AND blood_group=?"
        params.append(bg)

    if location:
        query += " AND location LIKE ? COLLATE NOCASE"
        params.append("%" + location + "%")

    query += " ORDER BY name COLLATE NOCASE"

    donors = conn.execute(query, params).fetchall()
    conn.close()

    return render_template(
        "search.html",
        donors=donors,
        selected_blood_group=bg,
        selected_location=location
    )


# Blood request form and submission
@app.route("/blood-request", methods=["GET", "POST"])
def blood_request():
    if request.method == "GET":
        return render_template("blood_request.html")

    requester_name = request.form.get("requester_name", "").strip()
    blood_group = request.form.get("blood_group", "").strip()
    units = request.form.get("units", "1").strip()
    hospital = request.form.get("hospital", "").strip()
    location = request.form.get("location", "").strip()
    contact_phone = request.form.get("contact_phone", "").strip()
    required_date = request.form.get("required_date", "").strip()
    notes = request.form.get("notes", "").strip()

    if not all([
        requester_name, blood_group, hospital,
        location, contact_phone, required_date
    ]):
        flash("Please fill in all required fields.", "danger")
        return redirect("/blood-request")

    try:
        units = int(units)
        if units < 1:
            raise ValueError
        date.fromisoformat(required_date)
    except ValueError:
        flash("Please enter valid units and required date.", "danger")
        return redirect("/blood-request")

    conn = get_db()
    conn.execute("""
        INSERT INTO blood_requests (
            requester_name, blood_group, units, hospital,
            location, contact_phone, required_date, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        requester_name, blood_group, units, hospital,
        location, contact_phone, required_date, notes
    ))
    conn.commit()
    conn.close()

    flash("Blood request submitted successfully!", "success")
    return redirect("/blood-request")


# ==============================
# ADMIN LOGIN
# ==============================
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if "admin_id" in session:
        return redirect(url_for("admin_dashboard"))

    if request.method == "GET":
        return render_template("admin_login.html")

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        flash("Please enter username and password.", "danger")
        return redirect(url_for("admin_login"))

    conn = get_db()
    admin = conn.execute(
        "SELECT * FROM admins WHERE username=?",
        (username,)
    ).fetchone()
    conn.close()

    if (
        not admin
        or not check_password_hash(admin["password_hash"], password)
    ):
        flash("Invalid admin username or password.", "danger")
        return redirect(url_for("admin_login"))

    session.clear()
    session["admin_id"] = admin["id"]
    session["admin_username"] = admin["username"]

    flash("Admin login successful!", "success")
    return redirect(url_for("admin_dashboard"))


# ==============================
# ADMIN DASHBOARD
# ==============================
@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    conn = get_db()

    donor_count = conn.execute(
        "SELECT COUNT(*) FROM donors"
    ).fetchone()[0]

    eligible_count = conn.execute(
        "SELECT COUNT(*) FROM donors WHERE is_eligible=1"
    ).fetchone()[0]

    request_count = conn.execute(
        "SELECT COUNT(*) FROM blood_requests"
    ).fetchone()[0]

    pending_count = conn.execute(
        "SELECT COUNT(*) FROM blood_requests WHERE status='Pending'"
    ).fetchone()[0]

    requests = conn.execute("""
        SELECT *
        FROM blood_requests
        ORDER BY created_at DESC, id DESC
    """).fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        donor_count=donor_count,
        eligible_count=eligible_count,
        request_count=request_count,
        pending_count=pending_count,
        requests=requests,
        admin_username=session.get("admin_username")
    )


# ==============================
# UPDATE BLOOD REQUEST STATUS
# ==============================
@app.route("/admin/request/<int:request_id>/status", methods=["POST"])
@admin_required
def update_request_status(request_id):
    status = request.form.get("status", "").strip()
    allowed_statuses = {"Pending", "Fulfilled", "Cancelled"}

    if status not in allowed_statuses:
        flash("Invalid request status.", "danger")
        return redirect(url_for("admin_dashboard"))

    conn = get_db()
    result = conn.execute(
        "UPDATE blood_requests SET status=? WHERE id=?",
        (status, request_id)
    )
    conn.commit()
    updated = result.rowcount
    conn.close()

    if updated == 0:
        flash("Blood request not found.", "danger")
    else:
        flash("Blood request status updated successfully!", "success")

    return redirect(url_for("admin_dashboard"))


# ==============================
# ADMIN LOGOUT
# ==============================
@app.route("/admin/logout", methods=["POST"])
@admin_required
def admin_logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("admin_login"))


@app.route("/firebase-messaging-sw.js")
def firebase_messaging_sw():
    return send_from_directory(
        app.root_path,
        "firebase-messaging-sw.js",
        mimetype="application/javascript"
    )


# ==============================
# CREATE ADMIN ACCOUNT
# ==============================
@app.cli.command("create-admin")
def create_admin():
    """Create an administrator account."""
    username = input("Enter admin username: ").strip()

    if not username:
        print("Username cannot be empty.")
        return

    password = getpass("Enter admin password: ")
    confirm = getpass("Confirm admin password: ")

    if len(password) < 8:
        print("Password must contain at least 8 characters.")
        return

    if password != confirm:
        print("Passwords do not match.")
        return

    conn = get_db()

    try:
        conn.execute(
            "INSERT INTO admins (username, password_hash) VALUES (?, ?)",
            (username, generate_password_hash(password))
        )
        conn.commit()
        print("Admin account created successfully!")
    except sqlite3.IntegrityError:
        print("This admin username already exists.")
    finally:
        conn.close()


setup_database()

if __name__ == "__main__":
    app.run(debug=True)
