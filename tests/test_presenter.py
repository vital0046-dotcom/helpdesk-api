import threading

import pytest
from werkzeug.serving import make_server

from helpdesk.extensions import db
from helpdesk.models import Category, Comment, Ticket, User
from tools.demo_presenter import DemoSession


@pytest.fixture
def http_api(app):
    app.config["API_KEY"] = "test-only-presentation-key"
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", app.config["API_KEY"]
    server.shutdown()
    thread.join(timeout=3)
    server.server_close()


def test_presenter_replays_collection_and_cleans_only_its_records(http_api, app):
    session = DemoSession(*http_api, timeout=3)
    results = [session.execute_next() for _ in range(14)]
    assert all(result["passed"] for result in results)
    assert results[5]["status"] == 409
    assert session.position == 14
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Ticket)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(Comment)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(User)) == 1
        assert db.session.scalar(db.select(db.func.count()).select_from(Category)) == 2


def test_presenter_does_not_advance_after_authentication_failure(http_api):
    session = DemoSession(http_api[0], "wrong-key", timeout=3)
    assert session.execute_next()["passed"]
    result = session.execute_next()
    assert result["status"] == 401
    assert not result["passed"]
    assert session.position == 1
    assert "user_id" not in session.variables
