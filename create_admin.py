import getpass
import psycopg2
from werkzeug.security import generate_password_hash
from db import get_connection


def create_user():
    print("=== Create Portal Administrator Account ===")
    full_name = input("Full Name (e.g. Victor Otieno): ").strip()
    username = input("Choose Username: ").strip()
    password = getpass.getpass("Choose Password: ")
    confirm = getpass.getpass("Confirm Password: ")

    if not all([full_name, username, password]):
        print("Error: All fields are required.")
        return

    if password != confirm:
        print("Error: Passwords do not match.")
        return

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
            cur.execute(
                """
                INSERT INTO users (username, password_hash, full_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (username) DO UPDATE
                SET password_hash = EXCLUDED.password_hash,
                    full_name = EXCLUDED.full_name
                """,
                (username, generate_password_hash(password), full_name),
            )
        conn.commit()
        print(f"Success! Account '{username}' is ready.")
    except psycopg2.Error as e:
        conn.rollback()
        print(f"Database error: {e}")
    finally:
        conn.close()


if __name__ == "__main__":
    create_user()