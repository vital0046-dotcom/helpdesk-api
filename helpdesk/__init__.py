import hmac
import json
import logging
import os
import sqlite3
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import click
from flask import Flask, abort, g, jsonify, request
from flask_cors import CORS
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.exceptions import HTTPException

from .extensions import db, migrate


@event.listens_for(Engine, "connect")
def sqlite_constraints(connection, record):
    if isinstance(connection, sqlite3.Connection):
        connection.execute("PRAGMA foreign_keys=ON")


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    url = os.getenv("DATABASE_URL", "sqlite:///helpdesk.db")
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg://" + url[len(prefix) :]
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        API_KEY=os.getenv("API_KEY", ""),
        APP_ENV=os.getenv("APP_ENV", "development"),
        MAX_CONTENT_LENGTH=64 * 1024,
        LOG_FILE=os.getenv("LOG_FILE", "logs/requests.jsonl"),
        CORS_ORIGINS=[x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()],
    )
    if config:
        app.config.update(config)
    if app.config["APP_ENV"] == "production" and len(app.config["API_KEY"]) < 32:
        raise RuntimeError("Production requires API_KEY with at least 32 characters")
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    migrate.init_app(app, db)
    app.json.ensure_ascii = False
    if app.config["CORS_ORIGINS"]:
        CORS(
            app,
            resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
            allow_headers=["Content-Type", "X-API-Key"],
        )

    from .routes import api

    app.register_blueprint(api)
    request_logger = logging.getLogger(f"helpdesk.requests.{id(app)}")
    request_logger.setLevel(logging.INFO)
    request_logger.propagate = False
    if app.config["LOG_FILE"]:
        path = Path(app.config["LOG_FILE"])
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        request_logger.addHandler(handler)
    else:
        request_logger.addHandler(logging.NullHandler())

    @app.before_request
    def before_request():
        g.started = time.perf_counter()
        if request.path.startswith("/api/") and request.method != "OPTIONS":
            expected = app.config["API_KEY"]
            provided = request.headers.get("X-API-Key", "")
            if expected and not hmac.compare_digest(provided.encode(), expected.encode()):
                abort(401, description="Missing or invalid X-API-Key")

    @app.after_request
    def after_request(response):
        request_logger.info(
            json.dumps(
                {
                    "time": datetime.now(timezone.utc).isoformat(),
                    "method": request.method,
                    "path": request.url_rule.rule if request.url_rule else "<unmatched>",
                    "status": response.status_code,
                    "duration_ms": round(
                        (time.perf_counter() - g.get("started", time.perf_counter())) * 1000, 3
                    ),
                },
                ensure_ascii=False,
            )
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        response = error.get_response()
        response.data = app.json.dumps(
            {"error": {"code": error.code, "message": error.description}}
        )
        response.content_type = "application/json"
        return response

    @app.errorhandler(IntegrityError)
    def conflict(error):
        db.session.rollback()
        return jsonify(
            error={"code": 409, "message": "Duplicate value or conflicting database reference"}
        ), 409

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return jsonify(error={"code": 500, "message": "Internal server error"}), 500

    @app.get("/")
    def index():
        return {
            "service": "Helpdesk API",
            "version": "1.0.0",
            "health": "/health",
            "documentation": "See README.md and docs/API.md in the project repository",
        }

    @app.get("/health")
    def health():
        try:
            db.session.execute(text("SELECT 1"))
        except SQLAlchemyError:
            db.session.rollback()
            return {"status": "unavailable"}, 503
        return {"status": "ok"}

    @app.cli.command("seed")
    def seed():
        """Add fictitious demo users/categories and one ticket; safe to repeat."""
        from .models import Category, Ticket, User

        for name in ["Оборудование", "Программы", "Сеть", "Другое"]:
            if not db.session.scalar(db.select(Category).where(Category.name == name)):
                db.session.add(Category(name=name))
        db.session.flush()
        user = db.session.scalar(db.select(User).where(User.email == "student@example.test"))
        if user is None:
            user = User(name="Демо-студент", email="student@example.test")
            db.session.add(user)
            db.session.flush()
        if not db.session.scalar(db.select(Ticket.id).limit(1)):
            category = db.session.scalar(db.select(Category).where(Category.name == "Оборудование"))
            db.session.add(
                Ticket(
                    title="Не работает принтер",
                    description="Учебная заявка: принтер не печатает.",
                    author_id=user.id,
                    category_id=category.id,
                    priority="medium",
                )
            )
        db.session.commit()
        click.echo("Demo data ready")

    return app
