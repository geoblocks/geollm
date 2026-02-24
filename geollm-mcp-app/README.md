# GeoLLM MCP App

MCP App that exposes the `parse_geo_query` tool with an embedded OpenLayers map UI.

## Why two servers

The [`@modelcontextprotocol/ext-apps`](https://www.npmjs.com/package/@modelcontextprotocol/ext-apps) SDK - which handles MCP App resource registration and the `ui://` scheme - only has a TypeScript/Node implementation. There is no Python equivalent yet.

The GeoLLM parsing logic lives in Python (`geollm` package + LangChain + OpenAI). Rather than re-implement it in TypeScript, the architecture uses a thin TypeScript proxy that speaks MCP to the host and delegates all tool logic to a Python backend over HTTP.

## Architecture

```
MCP Host (VS Code / Claude Desktop)
        │  MCP / StreamableHTTP
        ▼
┌──────────────────────────────────┐
│  server.ts  (Node, port 3002)    │  ← registers tool + ui:// resource
│  @modelcontextprotocol/ext-apps  │
└────────────┬─────────────────────┘
             │  POST /api/parse_geo_query  (HTTP)
             ▼
┌──────────────────────────────────┐
│  mcp_server.py  (Python, :8000)  │  ← runs GeoFilterParser via LangChain
│  FastMCP + uvicorn               │
└──────────────────────────────────┘
```

**server.ts**

- Registers the `parse_geo_query` tool with the MCP host using `registerAppTool`.
- On tool invocation, forwards `user_query` to the Python backend and returns the JSON response as a text content block.
- Registers the built single-file HTML (`dist/mcp-app.html`) as a `ui://` resource with the correct MIME type (`text/html;profile=mcp-app`).

**mcp_server.py**

- Loads the `geollm` package, SwissNames3D data, and a LangChain `ChatOpenAI` instance.
- Exposes `POST /api/parse_geo_query` (consumed by the TS proxy) and a native MCP tool registered via FastMCP.
- Returns a `QueryResponse` containing the parsed `GeoQuery` and a GeoJSON `FeatureCollection`.
- The native MCP tool can be used standalone (without the TS proxy or any MCP App UI) by pointing an MCP host directly at `http://127.0.0.1:8000/mcp`. This is useful when the map panel is not needed and you want to avoid the Node dependency entirely.

**src/mcp-app.ts** (browser)

- Runs inside any MCP host that supports the `ui://` scheme (e.g. VS Code, Claude Desktop).
- Uses `@modelcontextprotocol/ext-apps` `App` to receive `ontoolinput` / `ontoolresult` callbacks from the host and to call `callServerTool` from the UI.
- Renders results on an OpenLayers map.

## Local development

**Prerequisites**: Node 22+, Python 3.12+, `uv`, an OpenAI API key.

```bash
# 1. Install Python deps and activate the venv
uv sync --extra dev
source .venv/bin/activate


# 2. Install Node deps
cd geollm-mcp-app
npm install

# 3. Build the frontend bundle
npm run build          # produces dist/mcp-app.html

# 4. Start the Python backend
OPENAI_API_KEY=sk-... uv run geollm-mcp-app/mcp_server.py

# 5. Start the TypeScript MCP proxy
cd geollm-mcp-app
npm run serve          # listens on http://localhost:3002/mcp
```

Add the server to `.vscode/mcp.json` (or the equivalent config for your MCP client):

```json
{
  "servers": {
    "GeoLLM": {
      "url": "http://127.0.0.1:3002/mcp",
      "type": "http"
    }
  }
}
```

## Docker

Build context must be the **repo root** (the Dockerfile copies `geollm/` and `pyproject.toml`).

```bash
cd geollm-mcp-app
cp .env.example .env   # set OPENAI_API_KEY
docker compose up --build
```

| Service          | Port | Description                                 |
| ---------------- | ---- | ------------------------------------------- |
| `python-backend` | 8000 | FastMCP / uvicorn                           |
| `ts-server`      | 3002 | Node MCP proxy - connect your MCP host here |

The SwissNames3D data directory (`../data` relative to `docker-compose.yml`) is mounted read-only into the Python container at `/data`.

## Environment variables

| Variable            | Default                 | Description                                                     |
| ------------------- | ----------------------- | --------------------------------------------------------------- |
| `OPENAI_API_KEY`    | -                       | Required. Passed to LangChain.                                  |
| `SWISSNAMES3D_PATH` | `data`                  | Path to the SwissNames3D shapefiles.                            |
| `HOST`              | `127.0.0.1`             | Bind address for the Python server. Set to `0.0.0.0` in Docker. |
| `PORT`              | `8000` / `3002`         | Port for Python / Node server respectively.                     |
| `PYTHON_API_URL`    | `http://127.0.0.1:8000` | URL of the Python backend, read by `server.ts`.                 |
