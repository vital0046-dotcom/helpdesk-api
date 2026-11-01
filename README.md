# Сервис заявок технической поддержки

[![Tests](https://github.com/vital0046-dotcom/helpdesk-api/actions/workflows/tests.yml/badge.svg)](https://github.com/vital0046-dotcom/helpdesk-api/actions/workflows/tests.yml)

Репозиторий: https://github.com/vital0046-dotcom/helpdesk-api.
Фактические результаты проверок: [docs/VALIDATION.md](docs/VALIDATION.md).

Демо API: https://helpdesk-api-3kw3.onrender.com.
Проверка доступности: https://helpdesk-api-3kw3.onrender.com/health.
Размещено 1 ноября 2026 года на Render Free с PostgreSQL. После простоя первый запрос
может занять около минуты; бесплатная база действует 30 дней с создания.
Методы `/api/*` требуют заголовок `X-API-Key` — ключ доступен владельцу в Render → Environment.

Учебный REST API на Python для регистрации и обработки обращений.
Тема практики: «Разработка REST API сервиса обработки заявок технической поддержки на языке Python».
Интерфейс сервиса — HTTP-запросы и JSON. Веб-кабинет, пароли пользователей и роли в первую версию не входят.

## Возможности

- CRUD заявок, пользователей и категорий.
- Комментарии к заявкам, чтение и удаление комментариев.
- Статусы `new`, `in_progress`, `closed`; приоритеты `low`, `medium`, `high`.
- Фильтры, поиск по заголовку и пагинация.
- Статистика по статусам, приоритетам и категориям (включая категории без заявок).
- Миграции базы, демонстрационные данные, тесты и обработчик JSONL-логов.
- Общий `X-API-Key` для закрытой демонстрации API на хостинге.

## Стек

Python 3.13, Flask, SQLAlchemy, Flask-Migrate/Alembic, PostgreSQL,
SQLite для быстрого локального старта, pytest, Docker, Gunicorn для Linux, Waitress для Windows.
Проверенные версии зафиксированы в `requirements.txt` и `requirements-dev.txt`.

## Быстрый запуск на Windows

### Окно для показа преподавателю

После установки окружения дважды нажми **Показать проект.cmd**. Откроется отдельное
окно с кнопками «Следующий шаг» и «Пройти показ целиком (01–11)». Это HTTP-клиент:
он выполняет реальные запросы из коллекции Postman, показывает отправленный JSON,
полученный ответ, HTTP-код и время. Шаг 06 должен вернуть 409 — проверяется запрет
неверного перехода статуса. Полный показ заканчивается закрытой заявкой и статистикой.

По умолчанию запускается локальный Flask API на свободном порту 127.0.0.1, с отдельной
SQLite `instance/presentation.db`, миграциями и временным API-ключом. Интернет не нужен.
При закрытии окна локальный сервер останавливается, база сохраняется. Шаги 12–14
удаляют только записи текущего сценария; «Новый сценарий» предыдущие записи не удаляет.

Второй режим — Render с PostgreSQL. Для него нужен локальный, исключённый из Git
файл `.env.render` с `API_KEY=...`. Ключ не показывается в окне и не входит в репозиторий.
У спящего бесплатного Render возможна задержка, поэтому для надёжного очного показа
предусмотрен локальный режим. Альтернативный запуск: `python -m tools.demo_presenter`.
Окно использует Tkinter из стандартной установки Python для Windows.

### Установка окружения и обычный запуск API

Открой папку проекта в VS Code и терминал PowerShell. Все команды ниже выполняются из корня проекта.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m flask --app wsgi db upgrade
.\.venv\Scripts\python.exe -m flask --app wsgi seed
.\.venv\Scripts\python.exe -m flask --app wsgi run --host 127.0.0.1 --port 8000
```

Если `.env` уже существует, не перезаписывай его. Активация окружения не обязательна:
в примерах запускается Python непосредственно из `.venv`. Повторный запуск с установкой
зависимостей и проверкой базы также доступен через `./start.ps1`, если запуск скриптов разрешён.

Проверка: <http://127.0.0.1:8000/health> вернёт `{"status":"ok"}`.
Список заявок: <http://127.0.0.1:8000/api/tickets>.
Остановка: `Ctrl+C` в терминале сервера. База SQLite: `instance/helpdesk.db`.

Для активации окружения: `.\.venv\Scripts\Activate.ps1`.
Если политика PowerShell запрещает активацию, используй полный путь к Python, как выше;
изменять системную политику не требуется.

## Linux и macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
flask --app wsgi db upgrade
flask --app wsgi seed
flask --app wsgi run --host 127.0.0.1 --port 8000
```

## Пример создания заявки

В PowerShell:

```powershell
$body = @{ title='Не работает принтер'; description='Не захватывает бумагу'; author_id=1; category_id=1; priority='high' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/tickets' -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
Invoke-RestMethod 'http://127.0.0.1:8000/api/tickets?status=new&page=1&per_page=10'
```

В Bash:

```bash
curl -X POST http://127.0.0.1:8000/api/tickets \
  -H 'Content-Type: application/json' \
  -d '{"title":"Printer broken","description":"No paper feed","author_id":1,"category_id":1,"priority":"high"}'
```

ID 1 относится к свежей базе после `seed`. В существующей базе сначала проверь `/api/users` и `/api/categories`.
Коллекция Postman: `examples/helpdesk.postman_collection.json`. В ней создаются собственные
категория, пользователь и заявка, а их ID сохраняются в переменные коллекции.

## Тестирование

```powershell
.\.venv\Scripts\python.exe -m pytest --cov=helpdesk --cov=tools --cov-report=term-missing
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pip check
```

Тесты по умолчанию используют отдельную временную SQLite, а не рабочую базу.
Для PostgreSQL установи `TEST_DATABASE_URL` на **отдельную одноразовую тестовую базу**:
фикстуры создают и удаляют её таблицы. Никогда не направляй эту переменную в рабочую базу.
GitHub Actions настроен на SQLite, PostgreSQL, миграции и сборку Docker.

Сохранить снимок своего окружения для изучения `pip freeze`:

```powershell
.\.venv\Scripts\python.exe -m pip freeze | Set-Content environment-freeze.txt
```

Файл `.in` содержит допустимые диапазоны версий; `.txt` — зафиксированные зависимости.
Windows-снимок `pip freeze` сам по себе не включает Gunicorn: он нужен только на Linux.

## PostgreSQL и Docker

Запусти Docker Desktop, затем:

```bash
docker compose up --build -d
docker compose exec api flask --app wsgi seed
docker compose ps
docker compose logs api
```

API доступен на <http://127.0.0.1:8000>, PostgreSQL на localhost:5432.
Перед этим останови локальный Flask, чтобы освободить порт 8000.
Compose предназначен для локальной разработки: порты привязаны к 127.0.0.1,
демонстрационный пароль БД можно заменить через `POSTGRES_PASSWORD` в `.env`.
Данные БД сохраняются в Docker volume. `docker compose down` останавливает сервисы,
не удаляя volume. Не добавляй `-v`, если данные нужны.

Можно запустить только базу: `docker compose up -d db`, а Flask оставить локально.
Тогда в `.env`: `DATABASE_URL=postgresql+psycopg://helpdesk:local-demo-password@localhost:5432/helpdesk`.
Настройки DBeaver и SQL-примеры — в [docs/SQL.md](docs/SQL.md).

## Структура

```text
helpdesk/          фабрика приложения, модели, обработчики и валидация
migrations/        версия схемы базы и миграции Alembic
tests/             тесты API, связей базы и анализа логов
tools/             обработчик логов и сравнение алгоритмов
examples/          Postman и учебные логи
docs/              описание API, деплоя, Git и план практики
deploy/            пример конфигурации nginx
Dockerfile         образ приложения
compose.yaml       приложение и PostgreSQL
wsgi.py            точка входа сервера
```

## Обработчик логов

```powershell
.\.venv\Scripts\python.exe -m tools.analyze_logs examples/requests.jsonl --repeat 10000
.\.venv\Scripts\python.exe -m tools.analyze_logs logs/requests.jsonl
```

Реализованы подсчёт вложенными циклами O(n·k) и один проход со словарём O(n)
в среднем, где k — число различных путей. Скрипт проверяет равенство результатов,
считает ошибки 4xx/5xx и измеряет время. На маленьком файле ускорение не гарантируется.
В логах API нет тел запросов, email, ключей и строки параметров URL.

## Ограничения учебной версии

Пользователи в таблице — авторы записей, а не учётные записи с паролями.
Любой владелец общего API-ключа может изменять все данные и выбирать автора.
Используй только вымышленные данные. Для реальной службы поддержки нужны отдельная
аутентификация, права доступа, аудит изменений и ограничения частоты запросов.
При `APP_ENV=production` запуск без API-ключа длиной минимум 32 символа запрещён.

Деплой: [docs/DEPLOY.md](docs/DEPLOY.md). Контракт API: [docs/API.md](docs/API.md).
План практики и защиты: [docs/PRACTICE.md](docs/PRACTICE.md). Git: [docs/GIT.md](docs/GIT.md).

## Источники

- [Flask: развёртывание](https://flask.palletsprojects.com/en/stable/deploying/)
- [Flask-SQLAlchemy: начало работы](https://flask-sqlalchemy.palletsprojects.com/en/stable/quickstart/)
- [Render: развёртывание Flask](https://render.com/docs/deploy-flask)
