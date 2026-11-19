import os
from functools import wraps
import psycopg2
from flask import Flask, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from db import get_connection, get_dict_cursor

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-to-a-long-random-secret-key")


def ensure_users_table():
    """Ensure the users table exists without inserting any default credentials."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id SERIAL PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    full_name VARCHAR(100) NOT NULL
                )
                """
            )
        conn.commit()
    finally:
        conn.close()


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login", error="Please sign in to access the Employee Portal."))
        return view_func(*args, **kwargs)

    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("index"))

    error = request.args.get("error", "")
    message = request.args.get("message", "")

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        conn = get_connection()
        try:
            with get_dict_cursor(conn) as cur:
                cur.execute(
                    "SELECT user_id, username, password_hash, full_name FROM users WHERE username = %s",
                    (username,),
                )
                user = cur.fetchone()
        finally:
            conn.close()

        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["user_id"]
            session["username"] = user["username"]
            session["full_name"] = user["full_name"]
            return redirect(url_for("index"))

        error = "Invalid username or password."

    return render_template("login.html", error=error, message=message)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login", message="You have been signed out."))


@app.route("/account", methods=["GET", "POST"])
@login_required
def account():
    error = request.args.get("error", "")
    message = request.args.get("message", "")

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        new_username = request.form.get("username", "").strip()
        current_password = request.form.get("current_password", "")
        new_password = request.form.get("new_password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not full_name or not new_username or not current_password:
            return redirect(url_for("account", error="Display name, username, and current password are required."))

        if new_password and new_password != confirm_password:
            return redirect(url_for("account", error="New passwords do not match."))

        conn = get_connection()
        try:
            with get_dict_cursor(conn) as cur:
                cur.execute(
                    "SELECT password_hash FROM users WHERE user_id = %s",
                    (session["user_id"],),
                )
                user = cur.fetchone()

                if not user or not check_password_hash(user["password_hash"], current_password):
                    return redirect(url_for("account", error="Current password is incorrect."))

                updated_hash = (
                    generate_password_hash(new_password) if new_password else user["password_hash"]
                )

                cur.execute(
                    """
                    UPDATE users
                    SET full_name = %s, username = %s, password_hash = %s
                    WHERE user_id = %s
                    """,
                    (full_name, new_username, updated_hash, session["user_id"]),
                )
            conn.commit()
            session["full_name"] = full_name
            session["username"] = new_username
            return redirect(url_for("account", message="Login credentials updated successfully."))
        except psycopg2.IntegrityError:
            conn.rollback()
            return redirect(url_for("account", error="That username is already taken."))
        except psycopg2.Error as e:
            conn.rollback()
            return redirect(url_for("account", error=f"Database error: {e.pgerror or e}"))
        finally:
            conn.close()

    return render_template("account.html", error=error, message=message)


@app.route("/")
@login_required
def index():
    search = request.args.get("search", "").strip()
    message = request.args.get("message", "")
    error = request.args.get("error", "")

    conn = get_connection()
    try:
        with get_dict_cursor(conn) as cur:
            if search:
                pattern = f"%{search}%"
                cur.execute(
                    """
                    SELECT empno, fname, lname, gender, salary, doe, deptcode, grade, role
                    FROM employee
                    WHERE empno ILIKE %s
                       OR fname ILIKE %s
                       OR lname ILIKE %s
                       OR deptcode ILIKE %s
                       OR COALESCE(role, '') ILIKE %s
                    ORDER BY empno ASC
                    """,
                    (pattern, pattern, pattern, pattern, pattern),
                )
            else:
                cur.execute(
                    """
                    SELECT empno, fname, lname, gender, salary, doe, deptcode, grade, role
                    FROM employee
                    ORDER BY empno ASC
                    """
                )
            employees = cur.fetchall()
    finally:
        conn.close()

    return render_template(
        "index.html",
        employees=employees,
        search=search,
        message=message,
        error=error,
    )


@app.route("/add", methods=["POST"])
@login_required
def add_employee():
    empno = request.form.get("empno", "").strip()
    fname = request.form.get("fname", "").strip()
    lname = request.form.get("lname", "").strip()
    gender = request.form.get("gender", "").strip()
    salary = request.form.get("salary", "").strip()
    doe = request.form.get("doe", "").strip()
    deptcode = request.form.get("deptcode", "").strip()
    grade = request.form.get("grade", "").strip()
    role = request.form.get("role", "").strip()

    if not all([empno, fname, lname, gender, salary, doe, deptcode, grade]):
        return redirect(url_for("index", error="All fields except Role are required."))

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (empno, fname, lname, gender, salary, doe, deptcode, grade, role)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (empno, fname, lname, gender, salary, doe, deptcode, grade, role or None),
            )
        conn.commit()
        return redirect(url_for("index", message=f"Employee {empno} saved."))
    except psycopg2.Error as e:
        conn.rollback()
        return redirect(url_for("index", error=f"Database error: {e.pgerror or e}"))
    finally:
        conn.close()


@app.route("/edit/<empno>", methods=["GET", "POST"])
@login_required
def edit_employee(empno):
    conn = get_connection()
    try:
        if request.method == "POST":
            fname = request.form.get("fname", "").strip()
            lname = request.form.get("lname", "").strip()
            gender = request.form.get("gender", "").strip()
            salary = request.form.get("salary", "").strip()
            doe = request.form.get("doe", "").strip()
            deptcode = request.form.get("deptcode", "").strip()
            grade = request.form.get("grade", "").strip()
            role = request.form.get("role", "").strip()

            if not all([fname, lname, gender, salary, doe, deptcode, grade]):
                return redirect(url_for("edit_employee", empno=empno, error="All fields except Role are required."))

            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE employee
                    SET fname = %s,
                        lname = %s,
                        gender = %s,
                        salary = %s,
                        doe = %s,
                        deptcode = %s,
                        grade = %s,
                        role = %s
                    WHERE empno = %s
                    """,
                    (fname, lname, gender, salary, doe, deptcode, grade, role or None, empno),
                )
            conn.commit()
            return redirect(url_for("index", message=f"Employee {empno} updated."))

        with get_dict_cursor(conn) as cur:
            cur.execute(
                """
                SELECT empno, fname, lname, gender, salary, doe, deptcode, grade, role
                FROM employee
                WHERE empno = %s
                """,
                (empno,),
            )
            employee = cur.fetchone()

        if not employee:
            return redirect(url_for("index", error=f"Employee {empno} not found."))

        return render_template("edit.html", employee=employee, error=request.args.get("error", ""))
    except psycopg2.Error as e:
        conn.rollback()
        return redirect(url_for("index", error=f"Database error: {e.pgerror or e}"))
    finally:
        conn.close()


@app.route("/delete/<empno>", methods=["POST"])
@login_required
def delete_employee(empno):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM employee WHERE empno = %s", (empno,))
        conn.commit()
        return redirect(url_for("index", message=f"Employee {empno} deleted."))
    except psycopg2.Error as e:
        conn.rollback()
        return redirect(url_for("index", error=f"Database error: {e.pgerror or e}"))
    finally:
        conn.close()


ensure_users_table()

if __name__ == "__main__":
    app.run(debug=True)