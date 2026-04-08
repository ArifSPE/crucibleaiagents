FROM python:3.11-slim

WORKDIR /workspace

ENV PIP_ROOT_USER_ACTION=ignore

COPY mcp_server/requirements.txt /tmp/mcp_requirements.txt
RUN pip install --no-cache-dir -U pip setuptools wheel \
    && pip install --no-cache-dir -r /tmp/mcp_requirements.txt

CMD ["python", "-m", "mcp_server.server"]
