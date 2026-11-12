"""Run locally; paste the result into Railway ADMIN_PASSWORD_HASH, never Git."""
from getpass import getpass
from argon2 import PasswordHasher

if __name__ == '__main__':
    password = getpass('New owner password (at least 16 characters): ')
    if len(password) < 16 or password != getpass('Repeat password: '):
        raise SystemExit('Passwords differ or password is too short')
    print(PasswordHasher().hash(password))
