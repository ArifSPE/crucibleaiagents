FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends tini nodejs npm && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 10001 runner
USER runner

WORKDIR /workspace

COPY --chown=runner:runner platform/ /opt/platform/
ENV PYTHONPATH=/opt/platform:/workspace/code
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "/opt/platform/run_agent.py"]
