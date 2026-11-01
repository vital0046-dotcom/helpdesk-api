import os

import pytest

from helpdesk import create_app
from helpdesk.extensions import db
from helpdesk.models import Category, User


@pytest.fixture
def app(tmp_path):
    # TEST_DATABASE_URL must point only to a disposable test database.
    app = create_app(
        {
            "TESTING": True,
            "APP_ENV": "testing",
            "API_KEY": "",
            "LOG_FILE": "",
            "SQLALCHEMY_DATABASE_URI": os.getenv(
                "TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}"
            ),
        }
    )
    with app.app_context():
        db.create_all()
        db.session.add_all(
            [
                User(name="Demo", email="demo@example.test"),
                Category(name="Hardware"),
                Category(name="Network"),
            ]
        )
        db.session.commit()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def ticket_data():
    return {
        "title": "Printer broken",
        "description": "No paper feed",
        "author_id": 1,
        "category_id": 1,
    }
