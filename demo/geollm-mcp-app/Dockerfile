# ── Stage 1: Vite frontend build ─────────────────────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app
COPY demo/geollm-mcp-app/package.json demo/geollm-mcp-app/package-lock.json ./
RUN npm ci
COPY demo/geollm-mcp-app/ .
RUN npm run build

# ── Stage 2: Python MCP backend ──────────────────────────────────────────────
FROM python:3.12-slim AS python-backend
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock ./
COPY geollm/ ./geollm/
RUN uv sync --frozen --group dev --extra dev

COPY demo/geollm-mcp-app/mcp_server.py .
COPY --from=builder /app/dist ./dist

EXPOSE 8000
CMD ["uv", "run", "python", "mcp_server.py"]

# ── Stage 3: TypeScript MCP proxy server ─────────────────────────────────────
FROM node:22-alpine AS ts-server
WORKDIR /app
COPY demo/geollm-mcp-app/package.json demo/geollm-mcp-app/package-lock.json ./
RUN npm ci
COPY demo/geollm-mcp-app/ .
COPY --from=builder /app/dist ./dist

EXPOSE 3002
CMD ["npx", "tsx", "server.ts"]
