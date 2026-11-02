"""HTTP client and private Postman exports shared by the desktop tools."""

import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ApiError(Exception):
    def __init__(self, status, message):
        self.status = status
        super().__init__(f"HTTP {status}: {message}")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward the API credential to another server after a redirect.
        return None


class ApiClient:
    def __init__(self, base_url, api_key, timeout=10, on_result=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.on_result = on_result
        self.opener = build_opener(NoRedirect)

    def request(self, method, path, body=None, params=None):
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("API path must be relative to the configured server")
        url = self.base_url + path
        if params:
            url += "?" + urlencode(params)
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        headers = {"X-API-Key": self.api_key}
        if data is not None:
            headers["Content-Type"] = "application/json"
        started = time.perf_counter()
        req = Request(url, data=data, headers=headers, method=method)
        try:
            response = self.opener.open(req, timeout=self.timeout)
        except HTTPError as error:
            response = error
        with response:
            status, raw = response.status, response.read().decode("utf-8")
        try:
            payload = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            payload = {"message": raw[:4000]}
        if self.on_result:
            self.on_result({"method": method, "url": url, "body": body, "status": status,
                            "response": payload, "ms": round((time.perf_counter() - started) * 1000)})
        if not 200 <= status < 300:
            message = payload.get("error", {}).get("message", raw[:1000]) if isinstance(payload, dict) else raw[:1000]
            raise ApiError(status, message)
        return payload

    def list_all(self, path):
        rows = []
        page = 1
        while True:
            result = self.request("GET", path, params={"page": page, "per_page": 100})
            rows.extend(result["items"])
            if page >= result["pages"]:
                return rows
            if page >= 1000:
                raise ValueError("Слишком много записей для списка выбора")
            page += 1


def export_postman(directory, base_url, api_key):
    """Write credentials only to an explicitly private, git-ignored local directory."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    environment = {
        "name": "Helpdesk — локальный API",
        "values": [{"key": "base_url", "value": base_url, "enabled": True},
                   {"key": "api_key", "value": api_key, "enabled": True, "type": "secret"}],
        "_postman_variable_scope": "environment",
    }
    environment_path = directory / "Helpdesk Local.postman_environment.json"
    environment_path.write_text(json.dumps(environment, ensure_ascii=False, indent=2), encoding="utf-8")
    root = Path(__file__).resolve().parents[1]
    collection = json.loads((root / "examples/helpdesk.postman_collection.json").read_text(encoding="utf-8"))
    collection["info"]["name"] = "Helpdesk — локальное управление"
    for variable in collection["variable"]:
        if variable["key"] == "base_url":
            variable["value"] = base_url
    # The key is supplied by the selected environment, never by this collection.
    manual = []
    specifications = [
        ("Список пользователей", "GET", "/api/users", None),
        ("Изменить пользователя", "PATCH", "/api/users/{{user_id}}", {"name": "Новое имя", "email": "student@example.test"}),
        ("Список категорий", "GET", "/api/categories", None),
        ("Изменить категорию", "PATCH", "/api/categories/{{category_id}}", {"name": "Оборудование"}),
        ("Все заявки", "GET", "/api/tickets?page=1&per_page=100", None),
        ("Получить заявку", "GET", "/api/tickets/{{ticket_id}}", None),
        ("Изменить заявку", "PATCH", "/api/tickets/{{ticket_id}}", {"title": "Не работает интернет", "description": "Нет соединения с сетью", "priority": "high"}),
        ("Редактировать комментарий", "PATCH", "/api/tickets/{{ticket_id}}/comments/{{comment_id}}", {"text": "Обновлённый комментарий"}),
        ("Удалить комментарий", "DELETE", "/api/tickets/{{ticket_id}}/comments/{{comment_id}}", None),
    ]
    for name, method, path, body in specifications:
        request = {"method": method, "url": "{{base_url}}" + path, "header": []}
        if body is not None:
            request["header"] = [{"key": "Content-Type", "value": "application/json"}]
            request["body"] = {"mode": "raw", "raw": json.dumps(body, ensure_ascii=False, indent=2),
                               "options": {"raw": {"language": "json"}}}
        manual.append({"name": name, "request": request})
    collection["item"] = [{"name": "Учебный сценарий 01–14", "item": collection["item"]},
                          {"name": "Ручное редактирование", "item": manual}]
    collection["variable"].append({"key": "comment_id", "value": ""})
    collection_path = directory / "Helpdesk Local.postman_collection.json"
    collection_path.write_text(json.dumps(collection, ensure_ascii=False, indent=2), encoding="utf-8")
    return environment_path, collection_path
