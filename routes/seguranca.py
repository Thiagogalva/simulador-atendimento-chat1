"""Proteção CSRF para os formulários HTML (os endpoints JSON dependem de Content-Type JSON + SameSite)."""
import hmac
import secrets

from flask import request, session


def token_csrf() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def csrf_valido() -> bool:
    enviado = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    esperado = session.get("csrf") or ""
    return bool(esperado) and hmac.compare_digest(enviado, esperado)
