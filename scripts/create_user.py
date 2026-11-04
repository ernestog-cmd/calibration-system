import getpass

from app.database import SessionLocal
from app.models import User, UserRole
from app.security import hash_password


def main() -> None:
    username = input("Username: ").strip()
    first_name = input("First name: ").strip()
    last_name = input("Last name: ").strip()
    role_input = input("Role (admin/technician/auditor): ").strip().lower()
    password = getpass.getpass("Password: ")

    if not username or not first_name or not last_name or not password:
        print("All fields are required.")
        return

    try:
        role = UserRole(role_input)
    except ValueError:
        print("Invalid role. Use admin, technician or auditor.")
        return

    with SessionLocal() as db:
        if db.get(User, username) is not None:
            print(f"The user '{username}' already exists.")
            return

        user = User(
            username=username,
            hashed_password=hash_password(password),
            first_name=first_name,
            last_name=last_name,
            role=role,
        )
        db.add(user)
        db.commit()

    print(f"User '{username}' created with role '{role.value}'.")


if __name__ == "__main__":
    main()