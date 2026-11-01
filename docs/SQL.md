# SQL и схема базы

Связи: users 1:N tickets; categories 1:N tickets; tickets 1:N comments; users 1:N comments.
При удалении заявки удаляются её комментарии. Удаление пользователя или категории,
на которых есть ссылки, запрещено. Все даты в UTC.

Примеры для учебной базы PostgreSQL (выполнять по одному, сверяя ID):

```sql
SELECT id, title, status FROM tickets ORDER BY created_at DESC LIMIT 10;

SELECT t.id, t.title, u.name AS author, c.name AS category
FROM tickets AS t
JOIN users AS u ON t.author_id = u.id
JOIN categories AS c ON t.category_id = c.id;

INSERT INTO categories (name) VALUES ('Учебная категория');
UPDATE categories SET name = 'Переименованная категория'
WHERE name = 'Учебная категория';
DELETE FROM categories WHERE name = 'Переименованная категория';

SELECT status, COUNT(*) FROM tickets GROUP BY status;
```

Через API действуют проверки переходов статуса. Прямые SQL-запросы обходят эти проверки;
используйте SQL-примеры только в учебной базе.

Для DBeaver после `docker compose up -d db` создайте соединение PostgreSQL:
host localhost, port 5432, database helpdesk, user helpdesk,
password из POSTGRES_PASSWORD (для локального примера: local-demo-password).
