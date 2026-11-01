FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home appuser
COPY --chown=appuser:appuser . .
RUN mkdir -p instance logs && chown -R appuser:appuser instance logs
USER appuser
EXPOSE 8000
CMD ["sh", "-c", "flask --app wsgi db upgrade && exec gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 4 --access-logfile - wsgi:app"]
