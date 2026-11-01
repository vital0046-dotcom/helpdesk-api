# Развёртывание

Этот файл описывает процедуру. Ссылка на работающий внешний сервис добавляется после
реального развёртывания; её наличие здесь не заявляется.

## Render с PostgreSQL

1. Загрузить содержимое папки проекта в отдельный GitHub-репозиторий `helpdesk-api`.
2. В Render создать PostgreSQL или подключить другую PostgreSQL. Проверить текущий
   тариф, ограничения и срок хранения данных перед подтверждением услуги.
3. Создать Web Service из репозитория, runtime Python, Python 3.13.
4. Build command: `pip install -r requirements.txt`.
5. Start command:

```bash
flask --app wsgi db upgrade && gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --access-logfile - wsgi:app
```

6. Переменные окружения:
   - `APP_ENV=production`
   - `DATABASE_URL` — адрес PostgreSQL из настроек хостинга, с учётными данными.
   - `API_KEY` — случайный ключ минимум 32 символа; не публиковать в репозитории.
   - `LOG_FILE=logs/requests.jsonl`
   - `CORS_ORIGINS` — оставить пустым, если работа только через Postman/curl.
7. Health check path: `/health`.
8. Проверить `/health`, затем `/api/tickets` с X-API-Key.
   Запрос без ключа должен возвращать 401. Создать учебные данные запросами Postman.
9. Записать фактическую ссылку сервиса в README и отчёт.

Сгенерировать ключ на своём компьютере: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
Не вставлять ключ в отчёт, URL или общедоступную коллекцию Postman.
`.env` автоматически читается командой flask; Gunicorn/Waitress получают переменные
из окружения процесса. На хостинге задавай их через настройки сервиса.
Не использовать файловую SQLite для постоянных данных на временной файловой системе хостинга.
Файловые логи также могут исчезнуть при пересоздании сервиса.

В production используется WSGI-сервер, а не встроенный сервер Flask:
[документация Flask](https://flask.palletsprojects.com/en/stable/deploying/).
Настройки Render сверены с [официальной инструкцией](https://render.com/docs/deploy-flask).

## Linux VPS

Установить Python 3.13, PostgreSQL, nginx, создать venv, установить requirements.txt,
задать переменные окружения и применить миграции. Пример nginx находится в `deploy/nginx.conf`.
Запуск приложения: `gunicorn --bind 127.0.0.1:8000 --workers 1 --threads 4 wsgi:app`.
В постоянной эксплуатации запускать через менеджер служб, настроить HTTPS и резервное копирование.

Для изучения screen можно временно запустить Gunicorn в сессии `screen -S helpdesk`.
Отсоединение: Ctrl+A, D; возвращение: `screen -r helpdesk`.
Это упражнение, а не замена менеджеру служб и автоматическому перезапуску.
