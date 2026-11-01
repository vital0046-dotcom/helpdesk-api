# Работа с Git

Выполнять из папки helpdesk-api. Не добавлять .env, .venv, базу и логи.
Если репозиторий уже инициализирован, первый шаг пропустить.

```bash
git init -b main
git add .
git status
git commit -m "Implement helpdesk REST API"
```

Если Git просит имя автора, укажи свои данные в локальной конфигурации репозитория:
`git config user.name "Твоё имя"` и `git config user.email "Твой GitHub noreply email"`.
Значения-заглушки в команды буквально не подставлять.

После создания пустого репозитория GitHub:

```bash
git remote add origin https://github.com/vital0046-dotcom/helpdesk-api.git
git push -u origin main
```

Публичный репозиторий: https://github.com/vital0046-dotcom/helpdesk-api.
Если origin уже существует, проверь `git remote -v` и не добавляй его повторно.
Вход выполняется через браузер/Git Credential Manager. Пароли и токены не пишутся в файлы проекта.

Работа с отдельной веткой:

```bash
git switch -c codex/readme-example
# Изменить файл README.md
git add README.md
git commit -m "Document another API example"
git switch main
git merge codex/readme-example
git push
git pull --ff-only
```

На другом компьютере после публикации:
`git clone https://github.com/vital0046-dotcom/helpdesk-api.git`.
