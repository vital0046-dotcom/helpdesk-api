from flask import Blueprint, abort, jsonify, request
from sqlalchemy import func

from .extensions import db
from .models import PRIORITIES, STATUSES, Category, Comment, Ticket, User
from .validation import choice, email, paginate, payload, positive_query, reference, text

api = Blueprint("api", __name__, url_prefix="/api")


def saved(obj, status=200):
    db.session.add(obj)
    db.session.commit()
    return jsonify(obj.to_dict()), status


@api.get("/users")
def users_list():
    return paginate(db.select(User).order_by(User.id))


@api.post("/users")
def users_create():
    data = payload({"name", "email"}, {"name", "email"})
    return saved(User(name=text(data["name"], "name", 100), email=email(data["email"])), 201)


@api.route("/users/<int:id>", methods=["GET", "PATCH", "DELETE"])
def users_detail(id):
    obj = db.get_or_404(User, id)
    if request.method == "GET":
        return obj.to_dict()
    if request.method == "DELETE":
        used = db.session.scalar(db.select(Ticket.id).where(Ticket.author_id == id).limit(1))
        commented = db.session.scalar(db.select(Comment.id).where(Comment.author_id == id).limit(1))
        if used is not None or commented is not None:
            abort(409, description="User has tickets or comments")
        db.session.delete(obj)
        db.session.commit()
        return "", 204
    data = payload({"name", "email"})
    if "name" in data:
        obj.name = text(data["name"], "name", 100)
    if "email" in data:
        obj.email = email(data["email"])
    return saved(obj)


@api.get("/categories")
def categories_list():
    return paginate(db.select(Category).order_by(Category.id))


@api.post("/categories")
def categories_create():
    data = payload({"name"}, {"name"})
    return saved(Category(name=text(data["name"], "name", 80)), 201)


@api.route("/categories/<int:id>", methods=["GET", "PATCH", "DELETE"])
def categories_detail(id):
    obj = db.get_or_404(Category, id)
    if request.method == "GET":
        return obj.to_dict()
    if request.method == "DELETE":
        if db.session.scalar(db.select(Ticket.id).where(Ticket.category_id == id).limit(1)):
            abort(409, description="Category is used by tickets")
        db.session.delete(obj)
        db.session.commit()
        return "", 204
    data = payload({"name"}, {"name"})
    obj.name = text(data["name"], "name", 80)
    return saved(obj)


def ticket_values(data):
    values = {}
    for field, maximum in [("title", 200), ("description", 10000)]:
        if field in data:
            values[field] = text(data[field], field, maximum)
    if "priority" in data:
        values["priority"] = choice(data["priority"], "priority", PRIORITIES)
    for field, model in [("author_id", User), ("category_id", Category)]:
        if field in data:
            values[field] = reference(data[field], model, field)
    return values


@api.post("/tickets")
def tickets_create():
    data = payload(
        {"title", "description", "priority", "author_id", "category_id"},
        {"title", "description", "author_id", "category_id"},
    )
    obj = Ticket(**ticket_values(data))
    response, status = saved(obj, 201)
    response.headers["Location"] = f"/api/tickets/{obj.id}"
    return response, status


@api.get("/tickets")
def tickets_list():
    allowed = {"status", "priority", "author_id", "category_id", "q", "page", "per_page"}
    if set(request.args) - allowed:
        abort(400, description="Unknown query parameter")
    stmt = db.select(Ticket)
    for field, options in [("status", STATUSES), ("priority", PRIORITIES)]:
        if field in request.args:
            value = choice(request.args[field], field, options)
            stmt = stmt.where(getattr(Ticket, field) == value)
    for field in ("author_id", "category_id"):
        value = positive_query(field)
        if value is not None:
            stmt = stmt.where(getattr(Ticket, field) == value)
    if "q" in request.args:
        value = text(request.args["q"], "q", 200)
        stmt = stmt.where(Ticket.title.icontains(value, autoescape=True))
    return paginate(stmt.order_by(Ticket.created_at.desc(), Ticket.id.desc()))


@api.route("/tickets/<int:id>", methods=["GET", "PATCH", "DELETE"])
def tickets_detail(id):
    obj = db.get_or_404(Ticket, id)
    if request.method == "GET":
        return obj.to_dict()
    if request.method == "DELETE":
        db.session.delete(obj)
        db.session.commit()
        return "", 204
    data = payload({"title", "description", "priority", "category_id", "status"})
    values = ticket_values(data)
    if "status" in data:
        new_status = choice(data["status"], "status", STATUSES)
        transitions = {"new": {"in_progress"}, "in_progress": {"closed"}, "closed": {"in_progress"}}
        if new_status != obj.status and new_status not in transitions[obj.status]:
            abort(409, description=f"Cannot transition from {obj.status} to {new_status}")
        values["status"] = new_status
    for field, value in values.items():
        setattr(obj, field, value)
    return saved(obj)


@api.route("/tickets/<int:id>/comments", methods=["GET", "POST"])
def comments(id):
    db.get_or_404(Ticket, id)
    if request.method == "GET":
        return paginate(db.select(Comment).where(Comment.ticket_id == id).order_by(Comment.id))
    data = payload({"text", "author_id"}, {"text", "author_id"})
    return saved(
        Comment(
            ticket_id=id,
            text=text(data["text"], "text", 5000),
            author_id=reference(data["author_id"], User, "author_id"),
        ),
        201,
    )


@api.delete("/tickets/<int:id>/comments/<int:comment_id>")
def comments_delete(id, comment_id):
    obj = db.get_or_404(Comment, comment_id)
    if obj.ticket_id != id:
        abort(404, description="Comment not found for this ticket")
    db.session.delete(obj)
    db.session.commit()
    return "", 204


@api.get("/stats")
def stats():
    by_status = dict.fromkeys(STATUSES, 0)
    by_priority = dict.fromkeys(PRIORITIES, 0)
    by_status.update(
        db.session.execute(db.select(Ticket.status, func.count()).group_by(Ticket.status)).all()
    )
    by_priority.update(
        db.session.execute(db.select(Ticket.priority, func.count()).group_by(Ticket.priority)).all()
    )
    grouped = db.session.execute(
        db.select(Category.id, Category.name, func.count(Ticket.id))
        .outerjoin(Ticket, Ticket.category_id == Category.id)
        .group_by(Category.id, Category.name)
        .order_by(Category.id)
    ).all()
    return {
        "total": sum(by_status.values()),
        "by_status": by_status,
        "by_priority": by_priority,
        "by_category": [{"id": id, "name": name, "count": count} for id, name, count in grouped],
    }
