"""Editable desktop client for the same REST API used by the presentation."""

import json
import os
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from tools.api_client import ApiClient, export_postman
from tools.demo_presenter import ROOT, start_local

STATUS = {"new": "Новая", "in_progress": "В работе", "closed": "Закрыта"}
PRIORITY = {"low": "Низкий", "medium": "Средний", "high": "Высокий"}
SPECS = {
    "tickets": {"title": "Заявки", "columns": [("id", "№", 50), ("title", "Название", 240),
                ("status", "Статус", 90), ("priority", "Приоритет", 90)],
                "fields": [("title", "Название", "entry"), ("description", "Описание", "text"),
                           ("author_id", "Автор", "users"), ("category_id", "Категория", "categories"),
                           ("priority", "Приоритет", "priority"), ("status", "Статус", "status")]},
    "users": {"title": "Пользователи", "columns": [("id", "№", 50), ("name", "Имя", 200),
              ("email", "Email", 240)], "fields": [("name", "Имя", "entry"), ("email", "Email", "entry")]},
    "categories": {"title": "Категории", "columns": [("id", "№", 50), ("name", "Название", 330)],
                   "fields": [("name", "Название", "entry")]},
    "comments": {"title": "Комментарии", "columns": [("id", "№", 50), ("text", "Комментарий", 330),
                 ("author_id", "Автор №", 80)], "fields": [("text", "Текст", "text"), ("author_id", "Автор", "users")]},
}


class ResourcePanel(ttk.Frame):
    def __init__(self, parent, host, kind, ticket_id=None):
        super().__init__(parent, padding=12)
        self.host, self.kind, self.ticket_id = host, kind, ticket_id
        self.spec = SPECS[kind]
        self.path = f"/api/tickets/{ticket_id}/comments" if kind == "comments" else f"/api/{kind}"
        self.page, self.pages, self.item = 1, 1, None
        self.rows, self.inputs, self.references = {}, {}, {"users": [], "categories": []}
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", pady=(0, 8))
        for title, action in [("Обновить", lambda: self.reload()), ("Новая запись", self.new)]:
            self.host.button(toolbar, title, action).pack(side="left", padx=(0, 8))
        self.query = tk.StringVar()
        self.filter_status = tk.StringVar(value="Все статусы")
        if kind == "tickets":
            search = self.host.track(ttk.Entry(toolbar, textvariable=self.query, width=25))
            search.pack(side="left", padx=(0, 8))
            search.bind("<Return>", lambda _e: self.reload(1))
            self.host.track(ttk.Combobox(toolbar, textvariable=self.filter_status, state="readonly",
                values=["Все статусы", *STATUS.values()], width=15)).pack(side="left", padx=(0, 8))
            self.host.button(toolbar, "Найти", lambda: self.reload(1)).pack(side="left")
        self.count = tk.StringVar(value="Загрузка…")
        ttk.Label(self, textvariable=self.count).pack(anchor="w", pady=(0, 8))
        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)
        listing, form = ttk.Frame(panes), ttk.Frame(panes, padding=(12, 0, 0, 0))
        panes.add(listing, weight=3)
        panes.add(form, weight=2)
        columns = [field for field, _, _ in self.spec["columns"]]
        self.tree = ttk.Treeview(listing, columns=columns, show="headings", selectmode="browse")
        for field, label, width in self.spec["columns"]:
            self.tree.heading(field, text=label)
            self.tree.column(field, width=width, minwidth=45)
        scroll = ttk.Scrollbar(listing, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.selected)
        pager = ttk.Frame(listing)
        pager.pack(fill="x", pady=(8, 0))
        self.host.button(pager, "← Предыдущая", lambda: self.reload(max(1, self.page - 1))).pack(side="left")
        self.host.button(pager, "Следующая →", lambda: self.reload(min(self.pages, self.page + 1))).pack(side="left", padx=8)
        self.record_title = tk.StringVar(value="Новая запись")
        ttk.Label(form, textvariable=self.record_title, font=("Segoe UI", 12, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        form.columnconfigure(1, weight=1)
        for row, (field, label, control) in enumerate(self.spec["fields"], start=1):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="nw", padx=(0, 8), pady=5)
            if control == "text":
                widget = tk.Text(form, height=5, width=32, wrap="word", font=("Segoe UI", 10))
            elif control in ("users", "categories", "status", "priority"):
                values = list(STATUS.values()) if control == "status" else list(PRIORITY.values()) if control == "priority" else []
                widget = ttk.Combobox(form, state="readonly", values=values, width=30)
            else:
                widget = ttk.Entry(form, width=34)
            self.inputs[field] = self.host.track(widget)
            widget.grid(row=row, column=1, sticky="ew", pady=5)
        actions = ttk.Frame(form)
        actions.grid(row=len(self.spec["fields"]) + 1, column=0, columnspan=2, sticky="ew", pady=10)
        self.host.button(actions, "Создать", self.create).pack(side="left", padx=(0, 6))
        self.host.button(actions, "Сохранить", self.save).pack(side="left", padx=(0, 6))
        self.host.button(actions, "Удалить", self.delete).pack(side="left")
        if kind == "tickets":
            actions2 = ttk.Frame(form)
            actions2.grid(row=len(self.spec["fields"]) + 2, column=0, columnspan=2, sticky="ew")
            self.host.button(actions2, "Комментарии", self.comments).pack(side="left", padx=(0, 6))
            self.host.button(actions2, "ID для Postman", self.copy_id).pack(side="left")
        self.new()

    def value(self, field):
        widget = self.inputs[field]
        return (widget.get("1.0", "end-1c") if isinstance(widget, tk.Text) else widget.get()).strip()

    def set_value(self, field, value):
        widget = self.inputs[field]
        state = str(widget.cget("state"))
        widget.configure(state="normal")
        if isinstance(widget, tk.Text):
            widget.delete("1.0", "end")
            widget.insert("1.0", str(value))
        elif isinstance(widget, ttk.Combobox):
            widget.set(str(value))
        else:
            widget.delete(0, "end")
            widget.insert(0, str(value))
        widget.configure(state=state)

    def new(self):
        if self.host.busy:
            return
        self.item = None
        self.tree.selection_remove(self.tree.selection())
        self.record_title.set("Новая запись — заполни поля и нажми «Создать»")
        for field, _label, control in self.spec["fields"]:
            widget = self.inputs[field]
            widget.configure(state="readonly" if isinstance(widget, ttk.Combobox) else "normal")
            value = ""
            if control in self.references and self.references[control]:
                value = self.option(self.references[control][0])
            if control == "priority":
                value = PRIORITY["medium"]
            if control == "status":
                value = STATUS["new"]
            self.set_value(field, value)
        if "status" in self.inputs:
            self.inputs["status"].configure(state="disabled")

    @staticmethod
    def option(record):
        return f"#{record['id']} — {record['name']}"

    def show_record(self, record):
        self.item = record
        self.record_title.set(f"Запись № {record['id']} — измени поля и нажми «Сохранить»")
        for field, _label, control in self.spec["fields"]:
            value = record.get(field, "")
            if control in self.references:
                match = next((r for r in self.references[control] if r["id"] == value), None)
                value = self.option(match) if match else f"#{value}"
            elif control == "priority":
                value = PRIORITY[value]
            elif control == "status":
                value = STATUS[value]
            self.set_value(field, value)
            if control == "status":
                self.inputs[field].configure(state="readonly")
        if "author_id" in self.inputs:
            self.inputs["author_id"].configure(state="disabled")

    def selected(self, _event=None):
        if self.host.busy:
            return
        selected = self.tree.selection()
        if selected and int(selected[0]) in self.rows:
            self.show_record(self.rows[int(selected[0])])

    def reload(self, page=None, select_id=None):
        if self.host.busy:
            return
        requested_page = page or self.page
        params = {"page": requested_page, "per_page": 50}
        if self.kind == "tickets":
            if self.query.get().strip():
                params["q"] = self.query.get().strip()
            if self.filter_status.get() in STATUS.values():
                params["status"] = next(k for k, v in STATUS.items() if v == self.filter_status.get())

        def fetch():
            result = self.host.client.request("GET", self.path, params=params)
            if result["pages"] and result["pages"] < requested_page:
                params["page"] = result["pages"]
                result = self.host.client.request("GET", self.path, params=params)
            references = {}
            for control in {c for _, _, c in self.spec["fields"]} & {"users", "categories"}:
                references[control] = self.host.client.list_all("/api/" + control)
            return result, references

        def display(bundle):
            if not self.winfo_exists():
                return
            result, references = bundle
            self.page, self.pages = result["page"], max(1, result["pages"])
            self.references.update(references)
            for field, _, control in self.spec["fields"]:
                if control in references:
                    options = [self.option(r) for r in references[control]]
                    self.inputs[field].configure(values=options)
                    if not self.value(field) and options:
                        self.set_value(field, options[0])
            self.tree.delete(*self.tree.get_children())
            self.rows = {row["id"]: row for row in result["items"]}
            for record in result["items"]:
                values = []
                for field, _, _ in self.spec["columns"]:
                    value = record[field]
                    if field == "status":
                        value = STATUS[value]
                    if field == "priority":
                        value = PRIORITY[value]
                    values.append(str(value).replace("\n", " "))
                self.tree.insert("", "end", iid=str(record["id"]), values=values)
            self.count.set(f"Страница {self.page} / {self.pages} · всего записей: {result['total']}")
            selected = select_id or (self.item["id"] if self.item else None)
            if selected in self.rows:
                self.tree.selection_set(str(selected))
                self.tree.see(str(selected))
                self.show_record(self.rows[selected])
        self.host.submit(fetch, display)

    def payload(self, create):
        body = {}
        for field, label, control in self.spec["fields"]:
            if field == "author_id" and not create:
                continue
            if field == "status" and create:
                continue
            value = self.value(field)
            if control in ("users", "categories"):
                if not value.startswith("#"):
                    raise ValueError(f"Выбери поле «{label}». При необходимости сначала создай пользователя или категорию.")
                value = int(value.split(" — ", 1)[0][1:])
            elif control == "priority":
                value = next(k for k, v in PRIORITY.items() if v == value)
            elif control == "status":
                value = next(k for k, v in STATUS.items() if v == value)
            elif not value:
                raise ValueError(f"Заполни поле «{label}»")
            body[field] = value
        return body

    def create(self):
        if self.item:
            messagebox.showinfo("Создание", "Нажми «Новая запись», чтобы создать отдельную запись. Для выбранной используй «Сохранить».", parent=self)
            return
        self.write(True)

    def save(self):
        if not self.item:
            messagebox.showinfo("Выбери запись", "Выбери строку в таблице, затем измени поля.", parent=self)
            return
        self.write(False)

    def write(self, create):
        try:
            body = self.payload(create)
        except (ValueError, StopIteration) as error:
            messagebox.showerror("Проверь поля", str(error) or "Выбери корректное значение", parent=self)
            return
        path = self.path if create else f"{self.path}/{self.item['id']}"

        def saved(record):
            if self.winfo_exists():
                self.show_record(record)
                self.reload(select_id=record["id"])
        self.host.submit(lambda: self.host.client.request("POST" if create else "PATCH", path, body), saved)

    def delete(self):
        if not self.item:
            return
        record_id = self.item["id"]
        extra = " Вместе с ней удалятся её комментарии." if self.kind == "tickets" else ""
        if not messagebox.askyesno("Удаление", f"Удалить запись № {record_id}?{extra} Отмены удаления нет.", parent=self):
            return

        def deleted(_result):
            if self.winfo_exists():
                self.new()
                self.reload()
        self.host.submit(lambda: self.host.client.request("DELETE", f"{self.path}/{record_id}"), deleted)

    def comments(self):
        if not self.item:
            messagebox.showinfo("Выбери заявку", "Сначала выбери заявку в таблице.", parent=self)
            return
        window = tk.Toplevel(self.host.root)
        window.title(f"Комментарии заявки № {self.item['id']}")
        window.geometry("1100x640")
        panel = ResourcePanel(window, self.host, "comments", self.item["id"])
        panel.pack(fill="both", expand=True)
        panel.reload(1)

    def copy_id(self):
        if self.item:
            self.host.copy(str(self.item["id"]))
            self.host.state.set(f"Скопирован ticket_id = {self.item['id']}. Укажи его в Variables коллекции Postman.")


class Editor:
    def __init__(self, root, base_url, api_key, server=None):
        self.root, self.server = root, server
        self.events = queue.Queue()
        self.busy = False
        self.pending_tab = False
        self.controls, self.saved_states = [], []
        self.client = ApiClient(base_url, api_key, timeout=10 if base_url.startswith("http://127.0.0.1:") else 90,
                                on_result=lambda result: self.events.put(("trace", result)))
        root.title("Helpdesk — управление заявками")
        root.geometry("1360x900")
        root.minsize(1060, 740)
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 10), padding=(9, 6))
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=29)
        outer = ttk.Frame(root, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Helpdesk · Управление заявками", font=("Segoe UI", 20, "bold")).pack(anchor="w")
        self.state = tk.StringVar(value=f"Подключено: {base_url}")
        ttk.Label(outer, textvariable=self.state, font=("Segoe UI", 10), wraplength=1280).pack(anchor="w", pady=(4, 10))
        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)
        self.panels = {}
        for kind in ("tickets", "users", "categories"):
            panel = ResourcePanel(self.notebook, self, kind)
            self.notebook.add(panel, text="  " + SPECS[kind]["title"] + "  ")
            self.panels[str(panel)] = panel
        stats = ttk.Frame(self.notebook, padding=14)
        self.notebook.add(stats, text="  Статистика  ")
        self.button(stats, "Обновить статистику", self.load_stats).pack(anchor="w", pady=(0, 10))
        self.stats_text = self.text_view(stats, height=13)
        connection = ttk.Frame(self.notebook, padding=18)
        self.notebook.add(connection, text="  Подключение / Postman  ")
        self.connection_panel(connection)
        trace = ttk.LabelFrame(outer, text="Последний HTTP-запрос — изменения выполняет настоящий API", padding=6)
        trace.pack(fill="x", pady=(12, 0))
        self.trace_text = self.text_view(trace, height=7)
        self.notebook.bind("<<NotebookTabChanged>>", self.tab_changed)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)
        root.after(150, lambda: next(iter(self.panels.values())).reload())

    def track(self, widget):
        self.controls.append(widget)
        return widget

    def button(self, parent, label, callback):
        return self.track(ttk.Button(parent, text=label, command=callback))

    @staticmethod
    def text_view(parent, height):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        text = tk.Text(frame, height=height, wrap="word", font=("Consolas", 10), bg="#f4f7fb", relief="flat", padx=10, pady=6)
        scroll = ttk.Scrollbar(frame, command=text.yview)
        text.configure(yscrollcommand=scroll.set, state="disabled")
        scroll.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        return text

    @staticmethod
    def put(widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def copy(self, value):
        self.root.clipboard_clear()
        self.root.clipboard_append(value)

    def connection_panel(self, frame):
        ttk.Label(frame, text="Редактор и Postman могут работать с одной базой", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 14))
        for label, value, secret in [("Адрес API", self.client.base_url, False), ("X-API-Key", self.client.api_key, True)]:
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=5)
            ttk.Label(row, text=label, width=16).pack(side="left")
            field = ttk.Entry(row, width=64, show="•" if secret else "")
            field.insert(0, value)
            field.configure(state="readonly")
            field.pack(side="left", padx=(0, 10))
            self.button(row, "Копировать", lambda v=value: self.copy(v)).pack(side="left")
        ttk.Label(frame, wraplength=1100, justify="left", text=(
            "Для Postman в браузере нужен Desktop Agent, запущенный на этом компьютере. "
            "Cloud Agent не имеет доступа к 127.0.0.1.\n\n"
            "1. Импортируй два файла из папки подключения.\n"
            "2. Справа вверху Postman выбери окружение «Helpdesk — локальный API».\n"
            "3. Внизу Postman выбери Desktop Agent.\n"
            "4. В коллекции «Helpdesk — локальное управление» открой запрос и нажми Send.\n\n"
            "Для своей существующей заявки установи ticket_id в Variables коллекции. "
            "Номер можно скопировать кнопкой «ID для Postman» в редакторе.\n"
            "Для учебного сценария 01–14 идентификаторы сохраняются автоматически. "
            "Файл окружения содержит локальный ключ; он исключён из Git.\n\n"
            "Пока работаешь в Postman, оставляй окно, запустившее локальный API, открытым."
        )).pack(anchor="w", pady=18)
        self.button(frame, "Сохранить файлы подключения", self.export).pack(anchor="w", pady=5)
        self.button(frame, "Открыть папку подключения", lambda: os.startfile(ROOT / "instance/postman")).pack(anchor="w", pady=5)

    def export(self):
        if not self.client.base_url.startswith("http://127.0.0.1:"):
            messagebox.showinfo("Локальное подключение", "Экспорт предназначен для локального сервера. Запусти редактор локально.", parent=self.root)
            return
        files = export_postman(ROOT / "instance/postman", self.client.base_url, self.client.api_key)
        self.state.set(f"Сохранены файлы Postman: {files[0].parent}")

    def tab_changed(self, _event=None):
        if self.busy:
            self.pending_tab = True
            return
        self.pending_tab = False
        if not self.busy:
            panel = self.panels.get(self.notebook.select())
            if panel:
                panel.reload()

    def load_stats(self):
        self.submit(lambda: self.client.request("GET", "/api/stats"),
                    lambda data: self.put(self.stats_text, json.dumps(data, ensure_ascii=False, indent=2)))

    def set_busy(self, busy):
        self.busy = busy
        if busy:
            self.saved_states = []
            for widget in self.controls:
                try:
                    self.saved_states.append((widget, widget.cget("state")))
                    widget.configure(state="disabled")
                except tk.TclError:
                    pass
        else:
            for widget, state in self.saved_states:
                try:
                    widget.configure(state=state)
                except tk.TclError:
                    pass
            self.saved_states.clear()

    def submit(self, job, callback):
        if self.busy:
            return
        self.set_busy(True)
        self.state.set(f"Выполняется запрос к {self.client.base_url}…")

        def worker():
            try:
                self.events.put(("done", (callback, job(), None)))
            except Exception as error:
                self.events.put(("done", (callback, None, error)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "trace":
                    body = json.dumps(value["body"], ensure_ascii=False, indent=2) if value["body"] else "(без тела)"
                    response = json.dumps(value["response"], ensure_ascii=False, indent=2) if value["response"] is not None else "(пусто)"
                    self.put(self.trace_text, f"{value['method']} {value['url']}\nX-API-Key: [скрыт]\n"
                             f"Запрос: {body}\n\nHTTP {value['status']} · {value['ms']} мс\n{response}")
                elif kind == "done":
                    callback, result, error = value
                    self.set_busy(False)
                    if error:
                        self.state.set(f"Запрос не выполнен: {error}")
                        messagebox.showerror("Ответ API", str(error), parent=self.root)
                    else:
                        self.state.set(f"Готово · {self.client.base_url} · изменения сохранены на сервере")
                        callback(result)
                    if self.pending_tab and not self.busy:
                        self.tab_changed()
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        if self.busy:
            messagebox.showinfo("Дождись ответа", "Сейчас выполняется запрос. Закрой окно после его завершения.", parent=self.root)
            return
        if self.server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        self.root.destroy()


def main():
    root = tk.Tk()
    root.title("Helpdesk — запуск редактора")
    root.geometry("560x120")
    loading = ttk.Label(root, text="Запускаю API и подключаю базу данных…", padding=24)
    loading.pack(fill="both", expand=True)
    events = queue.Queue()

    def start():
        try:
            events.put((start_local(port=8765, shared=True), None))
        except Exception as error:
            events.put((None, error))

    def finish():
        try:
            result, error = events.get_nowait()
        except queue.Empty:
            root.after(100, finish)
            return
        if error:
            loading.configure(text=f"Не удалось запустить API:\n{error}")
            return
        server, url, key = result
        loading.destroy()
        Editor(root, url, key, server)

    threading.Thread(target=start, daemon=True).start()
    root.after(100, finish)
    root.mainloop()


if __name__ == "__main__":
    main()
