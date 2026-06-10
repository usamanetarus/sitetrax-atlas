FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# PORT is set by Cloud Run; default to 8000 for local testing
ENV PORT=8000

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
