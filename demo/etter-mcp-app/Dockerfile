# Stage 1: Vite frontend build
FROM node:22-alpine AS builder
WORKDIR /app
COPY demo/etter-mcp-app/package.json demo/etter-mcp-app/package-lock.json ./
RUN npm ci
COPY demo/etter-mcp-app/ .
RUN npm run build

# Stage 2: Python FastAPI backend
FROM python:3.12-slim AS python-backend
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock ./
COPY etter/ ./etter/
RUN uv sync --frozen --group dev --extra dev

COPY demo/main.py ./demo/main.py
COPY demo/static/ ./demo/static/

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "demo.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Stage 3: TypeScript MCP proxy server
FROM node:22-alpine AS ts-server
WORKDIR /app
COPY demo/etter-mcp-app/package.json demo/etter-mcp-app/package-lock.json ./
RUN npm ci
COPY demo/etter-mcp-app/ .
COPY --from=builder /app/dist ./dist

EXPOSE 3002
CMD ["npx", "tsx", "server.ts"]
