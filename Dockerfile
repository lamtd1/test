FROM python:3.12-slim

WORKDIR /app

COPY requirement.txt .
RUN pip install --no-cache-dir -r requirement.txt

COPY . .

ENV PYTHONPATH=/app
ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "python scripts/seed.py && uvicorn src.main:app --host 0.0.0.0 --port ${PORT}"]
