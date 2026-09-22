from flask import Flask, render_template, request, redirect, flash
import sqlite3
from datetime import date
from pathlib import Path

app = Flask(__name__)
app.secret_key = "minor_project_secret_key_2026"

# Keep the database beside app.py, even if Flask is started from another folder.
DATABASE = Path(__file__).resolve().parent / "donors.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# --------------------------------------------------
# PRELIMINARY SCREENING RULES
# --------------------------------------------------
# These are prototype/project rules. Final donation eligibility
# must always be confirmed by authorized blood-centre staff.

MIN_AGE = 18
MIN_WEIGHT = 45.0
MIN_HEMOGLOBIN = 12.5
MIN_DAYS_BETWEEN_DONATIONS = 90
MAX_SCREENING_AGE_DAYS = 15


def check_eligibility(age, weight, last_donation_date,
                      screening_date, hemoglobin, pallor_observed):
    """Return (eligible, reason) using the project's preliminary rules."""

    if age < MIN_AGE:
        return False, "Age is below the prototype minimum of 18 years."

    if weight < MIN_WEIGHT:
        return False, "Weight is below the prototype minimum of 45 kg."

    if hemoglobin < MIN_HEMOGLOBIN:
        return False, "Hemoglobin is below the prototype threshold of 12.5 g/dL."

    if pallor_observed != "No":
        return False, "Pallor screening did not pass the prototype rule."

    try:
        screening = date.fromisoformat(screening_date)
    except (TypeError, ValueError):
        return False, "A valid health screening date is required."

    today = date.today()

    if screening > today:
        return False, "Health screening date cannot be in the future."

    screening_age = (today - screening).days
    if screening_age > MAX_SCREENING_AGE_DAYS:
        return False, "Health screening must be within the last 15 days."

    if last_donation_date:
        try:
            last_date = date.fromisoformat(last_donation_date)
        except (TypeError, ValueError):
            return False, "Last donation date is invalid."

        if last_date > today:
            return False, "Last donation date cannot be in the future."

        days_since_donation = (today - last_date).days
        if days_since_donation < MIN_DAYS_BETWEEN_DONATIONS:
            return False, "At least 90 days are required since the last donation under this prototype rule."

    return True, "Passed preliminary screening."


# --------------------------------------------------
# DATABASE SETUP / MIGRATION
# --------------------------------------------------

def init_db():
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
            available INTEGER DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()


def update_database():
    """Add columns needed by the current version to an older donors.db."""
    conn = get_db()
    columns = conn.execute("PRAGMA table_info(donors)").fetchall()
    existing = {column["name"] for column in columns}

    new_columns = {
        "gender": "TEXT",
        "height": "REAL",
        "bmi": "REAL",
        "bmi_status": "TEXT",
        "screening_date": "TEXT",
        "hemoglobin": "REAL",
        "pallor_observed": "TEXT",
        "consent": "INTEGER DEFAULT 0",
    }

    for name, definition in new_columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE donors ADD COLUMN {name} {definition}")

    conn.commit()
    conn.close()


def setup_database():
    init_db()
    update_database()


# --------------------------------------------------
# HOME PAGE
# --------------------------------------------------

@app.route("/")
def home():
    conn = get_db()
    donor_count = conn.execute("SELECT COUNT(*) FROM donors").fetchone()[0]
    eligible_count = conn.execute(
        "SELECT COUNT(*) FROM donors WHERE is_eligible = 1 AND available = 1"
    ).fetchone()[0]
    conn.close()

    return render_template(
        "index.html",
        donor_count=donor_count,
        eligible_count=eligible_count,
    )


# --------------------------------------------------
# DONOR REGISTRATION
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()
            blood_group = request.form.get("blood_group", "").strip()
            gender = request.form.get("gender", "").strip()
            phone = request.form.get("phone", "").strip()
            email = request.form.get("email", "").strip()
            location = request.form.get("location", "").strip()

            age = int(request.form.get("age", "0"))
            height_cm = float(request.form.get("height_cm", "0"))
            weight = float(request.form.get("weight", "0"))
            last_donation_date = request.form.get("last_donation_date", "").strip()
            screening_date = request.form.get("screening_date", "").strip()
            hemoglobin = float(request.form.get("hemoglobin", "0"))
            pallor_observed = request.form.get("pallor_observed", "").strip()
            consent = request.form.get("consent") == "on"

            if not name or not blood_group or not gender or not phone or not location:
                flash("Please fill in all required donor details.", "danger")
                return render_template("register.html")

            if not consent:
                flash("Consent is required for registration.", "danger")
                return render_template("register.html")

            if not (18 <= age <= 65):
                flash("Age must be between 18 and 65 for this prototype.", "danger")
                return render_template("register.html")

            if not (100 <= height_cm <= 250):
                flash("Please enter a valid height between 100 and 250 cm.", "danger")
                return render_template("register.html")

            if not (20 <= weight <= 250):
                flash("Please enter a valid weight between 20 and 250 kg.", "danger")
                return render_template("register.html")

            if not (0 < hemoglobin <= 25):
                flash("Please enter a valid hemoglobin value.", "danger")
                return render_template("register.html")

            # BMI is stored for the project record but is not used as a medical
            # diagnosis or as the sole donor eligibility decision.
            height_m = height_cm / 100
            bmi = round(weight / (height_m ** 2), 2)

            if bmi < 18.5:
                bmi_status = "Underweight"
            elif bmi < 25:
                bmi_status = "Normal"
            elif bmi < 30:
                bmi_status = "Overweight"
            else:
                bmi_status = "Obesity"

            eligible, reason = check_eligibility(
                age,
                weight,
                last_donation_date,
                screening_date,
                hemoglobin,
                pallor_observed,
            )

            conn = get_db()
            conn.execute("""
                INSERT INTO donors (
                    name, blood_group, gender, phone, email, location,
                    age, height, weight, bmi, bmi_status,
                    last_donation_date, screening_date, hemoglobin,
                    pallor_observed, consent, is_eligible, available
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, blood_group, gender, phone, email, location,
                age, height_cm, weight, bmi, bmi_status,
                last_donation_date or None, screening_date, hemoglobin,
                pallor_observed, int(consent), int(eligible), 1
            ))
            conn.commit()
            donor_id = conn.execute(
                "SELECT last_insert_rowid()"
            ).fetchone()[0]
            conn.close()

            flash(
                f"Registration successful! Your Donor ID is {donor_id}. Please save this ID.",
                "success"
            )

            return redirect("/search")

        except (ValueError, TypeError):
            flash("Please enter valid values in all numeric/date fields.", "danger")
            return render_template("register.html")
        except sqlite3.Error:
            flash("A database error occurred while saving the donor. Please try again.", "danger")
            return render_template("register.html")

    return render_template("register.html")


# --------------------------------------------------
# SEARCH DONORS
# --------------------------------------------------
@app.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        donor_id = request.form["donor_id"]
        phone = request.form["phone"]

        conn = get_db()

        donor = conn.execute(
            "SELECT * FROM donors WHERE id = ? AND phone = ?",
            (donor_id, phone)
        ).fetchone()

        conn.close()

        if not donor:
            flash("Invalid Donor ID or Phone Number.", "danger")
            return redirect("/profile")

        return render_template("profile.html", donor=donor)

    return render_template("profile_login.html")
@app.route("/profile/update/<int:donor_id>", methods=["POST"])
def update_profile(donor_id):

    name = request.form["name"]
    blood_group = request.form["blood_group"]
    phone = request.form["phone"]
    email = request.form["email"]
    location = request.form["location"]

    age = int(request.form["age"])
    height_cm = float(request.form["height_cm"])
    weight = float(request.form["weight"])

    last_donation_date = request.form["last_donation_date"]

    # Calculate BMI
    height_m = height_cm / 100
    bmi = weight / (height_m ** 2)

    if bmi < 18.5:
        bmi_status = "Underweight"
    elif bmi < 25:
        bmi_status = "Normal"
    elif bmi < 30:
        bmi_status = "Overweight"
    else:
        bmi_status = "Obesity"

    # Check preliminary eligibility again
    eligible = check_eligibility(
        age,
        weight,
        last_donation_date
    )

    conn = get_db()

    conn.execute("""
        UPDATE donors
        SET
            name = ?,
            blood_group = ?,
            phone = ?,
            email = ?,
            location = ?,
            age = ?,
            height = ?,
            weight = ?,
            bmi = ?,
            bmi_status = ?,
            last_donation_date = ?,
            is_eligible = ?
        WHERE id = ?
    """, (
        name,
        blood_group,
        phone,
        email,
        location,
        age,
        height_cm,
        weight,
        bmi,
        bmi_status,
        last_donation_date,
        int(eligible),
        donor_id
    ))

    conn.commit()
    conn.close()

    flash("Profile updated successfully!", "success")

    return redirect("/profile")
@app.route("/profile/availability/<int:donor_id>", methods=["POST"])
def update_availability(donor_id):

    available = request.form.get("available")

    if available == "1":
        new_status = 1
    else:
        new_status = 0

    conn = get_db()

    conn.execute(
        "UPDATE donors SET available = ? WHERE id = ?",
        (new_status, donor_id)
    )

    conn.commit()
    conn.close()

    flash("Availability status updated.", "success")

    return redirect("/profile")
@app.route("/search")
def search():
    blood_group = request.args.get("blood_group", "").strip()
    location = request.args.get("location", "").strip()

    conn = get_db()

    query = """
        SELECT id, name, blood_group, location
        FROM donors
        WHERE is_eligible = 1
          AND available = 1
    """
    parameters = []

    if blood_group:
        query += " AND blood_group = ?"
        parameters.append(blood_group)

    if location:
        query += " AND location LIKE ? COLLATE NOCASE"
        parameters.append("%" + location + "%")

    query += " ORDER BY name COLLATE NOCASE"

    donors = conn.execute(query, parameters).fetchall()
    conn.close()

    return render_template(
        "search.html",
        donors=donors,
        selected_blood_group=blood_group,
        selected_location=location,
    )


# --------------------------------------------------
# START APPLICATION
# --------------------------------------------------

setup_database()

if __name__ == "__main__":
    app.run(debug=True)
