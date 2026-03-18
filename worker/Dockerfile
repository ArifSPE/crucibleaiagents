FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends tini docker-cli && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY api /app/api
COPY worker /app/worker

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "/app/worker/worker.py"]
