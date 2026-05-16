FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080

EXPOSE 8080

CMD ["gunicorn", \
     "-k", "gevent", \
     "-w", "1", \
     "--worker-connections", "100", \
     "--timeout", "0", \
     "--log-level", "warning", \
     "-b", "0.0.0.0:8080", \
     "wsgi:app"]
