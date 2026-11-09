FROM python:3.13-slim-bookworm
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN pip install --no-cache-dir uv==0.11.3 && uv sync --locked --no-dev --no-cache
ENV PATH="/app/.venv/bin:${PATH}"
COPY alembic.ini ./
COPY agents ./agents
COPY backend ./backend
COPY scripts/__init__.py scripts/import_courses.py scripts/bootstrap_admin.py scripts/docker_backend.py ./scripts/
RUN useradd --create-home --uid 10001 learner
USER learner
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=6s --start-period=60s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=5).close()"
CMD ["python", "-m", "scripts.docker_backend"]
