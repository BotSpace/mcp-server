# syntax=docker/dockerfile:1
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

ENV MCP_HOST=0.0.0.0
ENV MCP_PORT=8200
EXPOSE 8200

CMD ["botspace-mcp"]
