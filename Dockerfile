FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LIBREOFFICE_PYTHON=/usr/bin/python3

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libreoffice-calc \
        python3-uno \
        fonts-dejavu \
        fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

COPY app app
COPY public public
COPY scripts scripts
COPY formOri formOri
COPY tests tests
COPY app_entry.py .
COPY pytest.ini .



RUN mkdir -p generated/pdfs generated/workbooks others

EXPOSE 3000

CMD ["gunicorn", "--bind", "0.0.0.0:3000", "--workers", "2", "--threads", "2", "--timeout", "240", "--access-logfile", "-", "--error-logfile", "-", "app_entry:app"]
