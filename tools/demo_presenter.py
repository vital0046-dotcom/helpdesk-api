"""A desktop presenter that sends real HTTP requests from the Postman collection."""

import json
import queue
import re
import secrets
import threading
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
REMOTE = "https://helpdesk-api-3kw3.onrender.com"
LABELS = [
    "Проверить сервер", "Создать автора", "Создать категорию", "Создать заявку",
    "Найти новые заявки", "Проверить запрет закрытия", "Взять в работу",
    "Добавить комментарий", "Прочитать комментарии", "Закрыть заявку",
    "Показать статистику", "Удалить тестовую заявку", "Удалить тестового автора",
    "Удалить тестовую категорию",
]
EXPLANATIONS = [
    "GET /health проверяет приложение и соединение с базой данных. Ожидается 200.",
    "POST создаёт тестового автора. Его id автоматически сохраняется для заявки.",
    "POST создаёт категорию. Её id автоматически сохраняется для заявки.",
    "POST создаёт связанную с автором и категорией заявку. Начальный статус — new.",
    "GET возвращает новые заявки высокого приоритета. page и per_page задают пагинацию.",
    "Ожидается 409: нельзя закрыть заявку непосредственно из new. Это успешная проверка правила.",
    "PATCH переводит заявку из new в in_progress — она взята в работу.",
    "POST добавляет комментарий, связанный с заявкой и автором.",
    "GET читает комментарии созданной заявки.",
    "PATCH переводит заявку из in_progress в closed — работа завершена.",
    "GET возвращает сводную статистику по заявкам в выбранной базе данных.",
    "DELETE удаляет только заявку текущего сценария и её комментарии. Ответ 204 пустой.",
    "DELETE удаляет только автора текущего сценария. Ответ 204 пустой.",
    "DELETE удаляет только категорию текущего сценария. Ответ 204 пустой.",
]


class DemoSession:
    def __init__(self, base_url, api_key, timeout=90):
        self.variables = {"base_url": base_url.rstrip("/")}
        self.api_key = api_key
        self.timeout = timeout
        self.position = 0
        self.items = json.loads(
            (ROOT / "examples/helpdesk.postman_collection.json").read_text(encoding="utf-8")
        )["item"]

    def expand(self, value):
        return re.sub(
            r"\{\{(.*?)\}\}",
            lambda m: str(uuid.uuid4()) if m[1] == "$guid" else str(self.variables[m[1]]),
            value,
        )

    def execute_next(self):
        index = self.position
        if index >= len(self.items):
            raise ValueError("Сценарий завершён")
        item = self.items[index]
        request = item["request"]
        url = self.expand(request["url"])
        body = request.get("body", {}).get("raw")
        body = self.expand(body) if body is not None else None
        headers = {h["key"]: h["value"] for h in request.get("header", [])}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        script = "\n".join(item["event"][0]["script"]["exec"])
        expected = int(re.search(r"\.status\((\d+)\)", script)[1])
        started = time.perf_counter()
        req = Request(url, data=body.encode() if body is not None else None,
                      headers=headers, method=request["method"])
        try:
            response = urlopen(req, timeout=self.timeout)
        except HTTPError as error:
            response = error
        with response:
            status, raw = response.status, response.read().decode("utf-8")
        elapsed = round((time.perf_counter() - started) * 1000)
        try:
            payload = json.loads(raw) if raw else None
            pretty = json.dumps(payload, ensure_ascii=False, indent=2) if raw else "(пустое тело ответа)"
        except json.JSONDecodeError:
            payload, pretty = None, raw[:16000]
        passed = status == expected
        if passed:
            for variable in re.findall(r'pm.collectionVariables.set\("(.*?)",', script):
                self.variables[variable] = payload["id"]
            self.position += 1
        return {"index": index, "method": request["method"], "url": url,
                "body": body, "status": status, "expected": expected,
                "elapsed": elapsed, "response": pretty, "passed": passed}


def start_local():
    """An isolated persistent SQLite database; only loopback is exposed."""
    from flask_migrate import upgrade
    from werkzeug.serving import make_server

    from helpdesk import create_app

    key = secrets.token_urlsafe(32)
    database = ROOT / "instance/presentation.db"
    app = create_app({
        "SQLALCHEMY_DATABASE_URI": "sqlite:///" + database.as_posix(),
        "API_KEY": key, "APP_ENV": "development", "CORS_ORIGINS": [],
        "LOG_FILE": str(ROOT / "logs/presentation.jsonl"),
    })
    with app.app_context():
        upgrade(directory=str(ROOT / "migrations"))
    server = make_server("127.0.0.1", 0, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}", key


class Presenter:
    def __init__(self, root):
        self.root = root
        self.server = None
        self.local_url = self.local_key = ""
        self.results = {}
        self.events = queue.Queue()
        self.busy = False
        self.session = None
        self.stopping = threading.Event()
        root.title("Helpdesk API — показ проекта")
        root.geometry("1200x820")
        root.minsize(950, 650)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TButton", padding=(12, 9), font=("Segoe UI", 11))
        style.configure("Treeview", rowheight=31, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        outer = ttk.Frame(root, padding=18)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Сервис заявок в техподдержку", font=("Segoe UI", 21, "bold")).pack(anchor="w")
        ttk.Label(outer, text="Иванов Виталий Григорьевич · Б-ИИПМИ-23 · настоящие HTTP-запросы к Flask API",
                  font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 14))
        bar = ttk.Frame(outer)
        bar.pack(fill="x")
        self.mode = tk.StringVar(value="Локально · SQLite · без интернета")
        self.selector = ttk.Combobox(bar, textvariable=self.mode, state="readonly", width=44,
                                    values=["Локально · SQLite · без интернета", "Render · PostgreSQL · интернет"])
        self.selector.pack(side="left")
        self.selector.bind("<<ComboboxSelected>>", self.change_mode)
        self.reset_button = ttk.Button(bar, text="Новый сценарий", command=self.reset)
        self.reset_button.pack(side="left", padx=8)
        self.state = tk.StringVar(value="Запускаю локальный API и применяю миграции…")
        ttk.Label(outer, textvariable=self.state, wraplength=1120, font=("Segoe UI", 10)).pack(anchor="w", pady=10)
        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(0, 12))
        self.next_button = ttk.Button(actions, text="Следующий шаг →", command=lambda: self.run(False))
        self.next_button.pack(side="left")
        self.all_button = ttk.Button(actions, text="Пройти показ целиком (01–11)", command=lambda: self.run(True))
        self.all_button.pack(side="left", padx=8)
        self.hint = tk.StringVar(value="Нажимай «Следующий шаг». В таблице можно открыть любой уже полученный ответ.")
        ttk.Label(outer, textvariable=self.hint, wraplength=1120, font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 12))
        panes = ttk.Panedwindow(outer, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left, right = ttk.Frame(panes), ttk.Frame(panes)
        panes.add(left, weight=2)
        panes.add(right, weight=3)
        self.tree = ttk.Treeview(left, columns=("step", "code"), show="headings", selectmode="browse")
        self.tree.heading("step", text="Шаг демонстрации")
        self.tree.heading("code", text="HTTP / итог")
        self.tree.column("step", width=285, minwidth=220)
        self.tree.column("code", width=110, minwidth=100)
        self.tree.pack(fill="both", expand=True)
        self.tree.tag_configure("pass", foreground="#16733e")
        self.tree.tag_configure("fail", foreground="#a32929")
        for i, label in enumerate(LABELS):
            self.tree.insert("", "end", iid=str(i), values=(f"{i+1:02d}. {label}", "—"))
        self.tree.bind("<<TreeviewSelect>>", self.show_selected)
        self.explanation = tk.StringVar(value=EXPLANATIONS[0])
        ttk.Label(right, textvariable=self.explanation, wraplength=620,
                  font=("Segoe UI", 11)).pack(fill="x", padx=(12, 0), pady=(0, 10))
        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True, padx=(12, 0))
        self.response_text = self.text_tab(notebook, "Ответ сервера")
        self.request_text = self.text_tab(notebook, "Отправленный запрос")
        ttk.Label(outer, text="Локальный режим: отдельная база presentation.db. Render: облачная база PostgreSQL. "
                  "Ключ не выводится. Шаги 12–14 удаляют только данные текущего сценария.",
                  wraplength=1120, font=("Segoe UI", 9)).pack(anchor="w", pady=(12, 0))
        self.set_busy(True)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)
        threading.Thread(target=self.prepare_local, daemon=True).start()

    @staticmethod
    def text_tab(notebook, name):
        frame = ttk.Frame(notebook)
        notebook.add(frame, text=name)
        text = tk.Text(frame, wrap="word", font=("Consolas", 11), bg="#f7f9fc",
                       fg="#17233a", relief="flat", padx=12, pady=12)
        scroll = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set, state="disabled")
        scroll.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        return text

    @staticmethod
    def put(text, value):
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", value)
        text.configure(state="disabled")

    def prepare_local(self):
        try:
            self.events.put(("ready", start_local()))
        except Exception as error:
            self.events.put(("error", f"Локальный запуск: {error}"))

    def set_busy(self, busy):
        self.busy = busy
        self.selector.configure(state="disabled" if busy else "readonly")
        self.reset_button.configure(state="disabled" if busy else "normal")
        done = not self.session or self.session.position >= 14
        self.next_button.configure(state="disabled" if busy or done else "normal")
        self.all_button.configure(state="disabled" if busy or not self.session or self.session.position >= 11 else "normal")

    def change_mode(self, _event=None):
        self.reset()

    def reset(self):
        remote = self.mode.get().startswith("Render")
        key = dotenv_values(ROOT / ".env.render").get("API_KEY", "") if remote else self.local_key
        if remote and not key:
            messagebox.showerror("Нужен ключ Render", "В локальном файле .env.render отсутствует API_KEY.")
            self.mode.set("Локально · SQLite · без интернета")
            remote, key = False, self.local_key
        url = REMOTE if remote else self.local_url
        self.session = DemoSession(url, key, timeout=90 if remote else 10)
        self.results.clear()
        for i, label in enumerate(LABELS):
            self.tree.item(str(i), values=(f"{i+1:02d}. {label}", "—"), tags=())
        self.put(self.response_text, "Здесь появится настоящий JSON-ответ API после первого шага.")
        self.put(self.request_text, "Здесь появится HTTP-метод, адрес и отправленный JSON.")
        self.state.set(f"Готово · {url} · {'PostgreSQL на Render' if remote else 'SQLite на этом компьютере'}")
        self.hint.set("Нажми «Следующий шаг» для проверки сервера. Новый сценарий не удаляет предыдущие записи.")
        self.set_busy(False)
        self.tree.selection_set("0")

    def run(self, all_steps):
        if self.busy or not self.session:
            return
        self.set_busy(True)
        session = self.session
        self.state.set("Отправляю запрос… Для спящего Render ожидание может занять до 90 секунд.")

        def worker():
            try:
                limit = 11 if all_steps else session.position + 1
                while session.position < limit and not self.stopping.is_set():
                    result = session.execute_next()
                    self.events.put(("result", result))
                    if not result["passed"]:
                        break
            except Exception as error:
                self.events.put(("error", f"Ответ не получен: {error}. При тайм-ауте Render выбери локальный режим."))
            finally:
                self.events.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()

    def show_selected(self, _event=None):
        selected = self.tree.selection()
        if not selected:
            return
        index = int(selected[0])
        self.explanation.set(EXPLANATIONS[index])
        result = self.results.get(index)
        if result:
            self.put(self.response_text, f"HTTP {result['status']} · ожидалось {result['expected']} · "
                     f"{result['elapsed']} мс\n\n{result['response']}")
            self.put(self.request_text, f"{result['method']} {result['url']}\n"
                     "X-API-Key: [скрыт]\n\n" + (result["body"] or "Без тела запроса"))
        else:
            self.put(self.response_text, "Этот шаг ещё не выполнен. Нажимай «Следующий шаг» по порядку.")
            self.put(self.request_text, "Запрос появится после выполнения шага.")

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "ready":
                    self.server, self.local_url, self.local_key = value
                    self.reset()
                elif kind == "result":
                    index = value["index"]
                    self.results[index] = value
                    passed = value["passed"]
                    self.tree.item(str(index), values=(f"{index+1:02d}. {LABELS[index]}",
                                   f"{value['status']} {'OK' if passed else 'ОШИБКА'}"),
                                   tags=("pass" if passed else "fail",))
                    self.tree.selection_set(str(index))
                    self.tree.see(str(index))
                    self.show_selected()
                    self.state.set(f"{self.mode.get()} · {self.session.position}/14 шагов · HTTP {value['status']}")
                    self.hint.set("Показ завершён: заявка закрыта. Выбери строку, чтобы объяснить ответ. "
                                  "Следующие шаги 12–14 удалят тестовые данные." if self.session.position == 11
                                  else "Следующий шаг продолжит сценарий. 409 на шаге 06 — ожидаемый отказ.")
                elif kind == "error":
                    self.state.set(value)
                    self.put(self.response_text, value)
                elif kind == "done":
                    self.set_busy(False)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        self.stopping.set()
        if self.server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        self.root.destroy()


def main():
    # Keep the HTTP runner importable on Linux servers without optional Tk libraries.
    global tk, messagebox, ttk
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    Presenter(root)
    root.mainloop()


if __name__ == "__main__":
    main()
