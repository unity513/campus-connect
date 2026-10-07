FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo zlib1g && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn==23.0.0 whitenoise==6.8.2

COPY . .

RUN python manage.py collectstatic --noinput || true

EXPOSE 8000
# Bind to all interfaces inside the container; put a reverse proxy / TLS in front.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
