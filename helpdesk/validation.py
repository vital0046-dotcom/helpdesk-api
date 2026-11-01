import re

from flask import abort, request

from .extensions import db


def payload(allowed, required=()):
    if not request.is_json:
        abort(415, description="Use Content-Type: application/json")
    data = request.get_json()
    if not isinstance(data, dict):
        abort(400, description="JSON body must be an object")
    if set(data) - set(allowed):
        abort(400, description="Unknown fields: " + ", ".join(sorted(set(data) - set(allowed))))
    if set(required) - set(data):
        abort(400, description="Missing fields: " + ", ".join(sorted(set(required) - set(data))))
    if not data:
        abort(400, description="Request body must not be empty")
    return data


def text(value, field, maximum):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        abort(400, description=f"{field} must contain 1..{maximum} characters")
    return value.strip()


def email(value):
    value = text(value, "email", 254).lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        abort(400, description="Invalid email address")
    return value


def choice(value, field, options):
    if not isinstance(value, str) or value not in options:
        abort(400, description=f"{field} must be one of: {', '.join(options)}")
    return value


def reference(value, model, field):
    if type(value) is not int or value <= 0:
        abort(400, description=f"{field} must be a positive integer")
    if db.session.get(model, value) is None:
        abort(400, description=f"Referenced {field} does not exist")
    return value


def positive_query(name, default=None, maximum=None):
    raw = request.args.get(name)
    if raw is None:
        return default
    if not re.fullmatch(r"[0-9]{1,9}", raw) or int(raw) < 1:
        abort(400, description=f"{name} must be a positive integer")
    value = int(raw)
    if maximum and value > maximum:
        abort(400, description=f"{name} must be <= {maximum}")
    return value


def paginate(statement):
    page = positive_query("page", 1)
    per_page = positive_query("per_page", 10, 100)
    result = db.paginate(statement, page=page, per_page=per_page, error_out=False)
    return {
        "items": [obj.to_dict() for obj in result.items],
        "page": page,
        "per_page": per_page,
        "total": result.total,
        "pages": result.pages,
    }
