FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1

WORKDIR /app

# Install deps
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy source
COPY src /app/src
COPY config /app/config
COPY demo /app/demo
COPY scripts /app/scripts
COPY README.md /app/README.md
COPY LICENSE /app/LICENSE
COPY pyproject.toml /app/pyproject.toml

# Create unprivileged user
RUN useradd -m -u 10001 appuser && chown -R appuser:appuser /app
USER appuser

ENV PYTHONPATH=/app/src

# Admin API binds to 127.0.0.1 inside container; map port if needed.
EXPOSE 8787

ENTRYPOINT ["python", "-m", "aimxs_gateway.main", "--config", "config/prototype.local.yaml"]
