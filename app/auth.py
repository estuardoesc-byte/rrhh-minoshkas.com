import secrets

import bcrypt
from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from .models import Usuario


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def autenticar(db: Session, email: str, password: str) -> Usuario | None:
    user = db.query(Usuario).filter(Usuario.email == email.strip().lower()).first()
    if user and user.activo and verify_password(password, user.password_hash):
        return user
    return None


class LoginRequired(Exception):
    pass


def usuario_actual(request: Request, db: Session) -> Usuario:
    uid = request.session.get("uid")
    user = db.get(Usuario, uid) if uid else None
    if not user or not user.activo:
        raise LoginRequired()
    return user


def csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf"] = token
    return token


def verificar_csrf(request: Request, token: str | None) -> None:
    esperado = request.session.get("csrf")
    if not esperado or not token or not secrets.compare_digest(esperado, token):
        raise HTTPException(status_code=403, detail="Formulario vencido. Recarga la página e intenta de nuevo.")
