import pytest
from sqlalchemy.exc import IntegrityError

from helpdesk import create_app
from helpdesk.extensions import db
from helpdesk.models import Ticket


def create(client, ticket_data, **changes):
    response = client.post("/api/tickets", json=ticket_data | changes)
    assert response.status_code == 201, response.json
    return response.json


def test_full_ticket_lifecycle(client, ticket_data):
    t = create(client, ticket_data)
    url = f"/api/tickets/{t['id']}"
    assert t["status"] == "new" and t["priority"] == "medium"
    assert client.get(url).json["title"] == ticket_data["title"]
    assert client.patch(url, json={"status": "closed"}).status_code == 409
    assert client.patch(url, json={"status": "in_progress"}).status_code == 200
    assert client.patch(url, json={"status": "closed", "priority": "high"}).status_code == 200
    assert client.patch(url, json={"status": "in_progress"}).status_code == 200
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404


@pytest.mark.parametrize(
    "changes",
    [
        {"title": " "},
        {"title": "x" * 201},
        {"description": None},
        {"author_id": True},
        {"author_id": 999},
        {"category_id": 0},
        {"category_id": "1"},
        {"priority": "urgent"},
        {"status": "closed"},
        {"extra": 1},
    ],
)
def test_invalid_ticket(client, ticket_data, changes):
    assert client.post("/api/tickets", json=ticket_data | changes).status_code == 400
    assert client.get("/api/tickets").json["total"] == 0


@pytest.mark.parametrize("body", [[], None, {}, {"title": "Missing fields"}])
def test_invalid_body(client, body):
    import json

    assert (
        client.post(
            "/api/tickets", data=json.dumps(body), content_type="application/json"
        ).status_code
        == 400
    )


def test_malformed_json_and_http_errors(client):
    assert client.post("/api/tickets", data="{").status_code == 415
    assert client.post("/api/tickets", data="{", content_type="application/json").status_code == 400
    assert client.get("/missing").json["error"]["code"] == 404
    assert client.put("/api/stats").status_code == 405
    assert "GET" in client.put("/api/stats").headers["Allow"]


def test_filters_pagination_and_literal_search(client, ticket_data):
    first = create(client, ticket_data, title="Printer 100%", priority="high")
    create(client, ticket_data, title="Network problem", category_id=2)
    create(client, ticket_data, title="Printer 100x")
    client.patch(f"/api/tickets/{first['id']}", json={"status": "in_progress"})
    result = client.get("/api/tickets?status=in_progress&priority=high&category_id=1").json
    assert result["total"] == 1 and result["items"][0]["id"] == first["id"]
    assert client.get("/api/tickets?q=100%25").json["total"] == 1
    pages = [client.get(f"/api/tickets?per_page=1&page={n}").json for n in [1, 2, 3]]
    assert len({r["items"][0]["id"] for r in pages}) == 3
    assert pages[0]["pages"] == 3
    assert client.get("/api/tickets?page=999").json["items"] == []


@pytest.mark.parametrize(
    "query", ["page=0", "per_page=101", "page=abc", "priority=no", "author_id=-1", "surprise=1"]
)
def test_invalid_queries(client, query):
    assert client.get("/api/tickets?" + query).status_code == 400


def test_comments_and_referential_integrity(client, ticket_data):
    t = create(client, ticket_data)
    base = f"/api/tickets/{t['id']}"
    c = client.post(base + "/comments", json={"text": "Checking", "author_id": 1})
    assert c.status_code == 201
    assert client.get(base + "/comments").json["total"] == 1
    assert client.delete(f"/api/tickets/999/comments/{c.json['id']}").status_code == 404
    assert client.delete("/api/users/1").status_code == 409
    assert client.delete("/api/categories/1").status_code == 409
    assert client.delete(base).status_code == 204
    assert client.delete(f"{base}/comments/{c.json['id']}").status_code == 404
    assert client.delete("/api/users/1").status_code == 204
    assert client.delete("/api/categories/1").status_code == 204


def test_stats_with_empty_categories(client, ticket_data):
    assert client.get("/api/stats").json["total"] == 0
    create(client, ticket_data, priority="high")
    stats = client.get("/api/stats").json
    assert stats["by_status"] == {"new": 1, "in_progress": 0, "closed": 0}
    assert stats["by_priority"]["high"] == 1
    assert stats["by_category"] == [
        {"id": 1, "name": "Hardware", "count": 1},
        {"id": 2, "name": "Network", "count": 0},
    ]


def test_unique_values_and_patch_atomicity(client, ticket_data):
    assert (
        client.post(
            "/api/users", json={"name": "Duplicate", "email": "DEMO@example.test"}
        ).status_code
        == 409
    )
    assert client.post("/api/categories", json={"name": "Hardware"}).status_code == 409
    t = create(client, ticket_data)
    url = f"/api/tickets/{t['id']}"
    assert client.patch(url, json={"title": "Changed", "status": "closed"}).status_code == 409
    assert client.get(url).json["title"] == ticket_data["title"]
    assert client.post("/api/users", json={"name": "Person", "email": "bad"}).status_code == 400


def test_database_rejects_broken_fk(app):
    with app.app_context():
        db.session.add(
            Ticket(title="Bad", description="Bad reference", author_id=999, category_id=1)
        )
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_api_key_and_public_health(app, client):
    app.config["API_KEY"] = "a" * 32
    assert client.get("/health").status_code == 200
    assert client.get("/api/tickets").status_code == 401
    assert client.get("/api/tickets", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/api/tickets", headers={"X-API-Key": "a" * 32}).status_code == 200


def test_production_requires_key():
    with pytest.raises(RuntimeError):
        create_app({"APP_ENV": "production", "API_KEY": ""})


def test_seed_idempotent(app):
    runner = app.test_cli_runner()
    assert runner.invoke(args=["seed"]).exit_code == 0
    assert runner.invoke(args=["seed"]).exit_code == 0
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Ticket)) == 1


def test_user_category_edits_and_comment_delete(client, ticket_data):
    user = client.post("/api/users", json={"name": "Other", "email": "other@example.test"}).json
    assert (
        client.patch(f"/api/users/{user['id']}", json={"name": "Updated"}).json["name"] == "Updated"
    )
    assert client.get(f"/api/users/{user['id']}").status_code == 200
    cat = client.post("/api/categories", json={"name": "Other"}).json
    assert (
        client.patch(f"/api/categories/{cat['id']}", json={"name": "Software"}).status_code == 200
    )
    assert client.get(f"/api/categories/{cat['id']}").json["name"] == "Software"
    assert client.get("/api/categories").json["total"] == 3
    assert client.get("/api/users").json["total"] == 2
    t = create(client, ticket_data)
    url = f"/api/tickets/{t['id']}/comments"
    comment = client.post(url, json={"text": "Done", "author_id": user["id"]}).json
    assert client.delete(url + f"/{comment['id']}").status_code == 204
    assert client.get(url).json["total"] == 0
    assert client.delete(f"/api/users/{user['id']}").status_code == 204


def test_comment_edit_validation_and_scope(client, ticket_data):
    ticket = create(client, ticket_data)
    base = f"/api/tickets/{ticket['id']}/comments"
    comment = client.post(base, json={"text": "Проверяю", "author_id": 1}).json
    path = f"{base}/{comment['id']}"
    assert client.patch(path, json={"text": "Исправлено"}).json["text"] == "Исправлено"
    assert client.patch(path, json={"text": ""}).status_code == 400
    assert client.patch(path, json={"text": "Другой", "author_id": 1}).status_code == 400
    assert client.patch(f"/api/tickets/999/comments/{comment['id']}", json={"text": "Ошибка"}).status_code == 404
    assert client.get(base).json["items"][0]["text"] == "Исправлено"
