// Registers the MCP App tool + resource and proxies tool calls to the Python backend.
console.log("Starting etter MCP App server...");

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { registerAppTool, registerAppResource, RESOURCE_MIME_TYPE } from "@modelcontextprotocol/ext-apps/server";
import cors from "cors";
import express from "express";
import fs from "node:fs/promises";
import path from "node:path";
import { z } from "zod";

const PYTHON_API_URL = process.env.PYTHON_API_URL ?? "http://127.0.0.1:8000";
const PORT = Number(process.env.PORT ?? 3002);

const resourceUri = "ui://parse_geo_query/mcp-app.html";

// CSP config: allow OSM tiles directly from the browser
const cspMeta = {
  ui: {
    csp: {
      connectDomains: ["https://*.openstreetmap.org"],
      resourceDomains: ["https://*.openstreetmap.org"],
    },
  },
};

// McpServer must be created per-request: the SDK disallows connecting the same
// instance to more than one transport.
function createServer(): McpServer {
  const server = new McpServer({
    name: "etter MCP App Server",
    version: "1.0.0",
  });

  registerAppTool(
    server,
    "parse_geo_query",
    {
      title: "etter Geo Query",
      description:
        "Transforms natural language location queries into structured geographic filters that can be used by search engines and spatial databases",
      inputSchema: {
        user_query: z
          .string()
          .describe(
            'The natural language query describing the geographic filter, e.g. "Find all locations within walking distance from Zurich main railway station"',
          ),
      },
      _meta: { ui: { resourceUri } },
    },
    async ({ user_query }) => {
      const response = await fetch(`${PYTHON_API_URL}/api/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: user_query }),
      });

      if (!response.ok) {
        const err = await response.text();
        throw new Error(`Python backend error (${response.status}): ${err}`);
      }

      const data = await response.json();
      return {
        content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }],
      };
    },
  );

  registerAppResource(server, resourceUri, resourceUri, { mimeType: RESOURCE_MIME_TYPE }, async () => {
    const html = await fs.readFile(path.join(import.meta.dirname, "dist", "mcp-app.html"), "utf-8");
    return {
      contents: [{ uri: resourceUri, mimeType: RESOURCE_MIME_TYPE, text: html, _meta: cspMeta }],
    };
  });

  return server;
}

const expressApp = express();
expressApp.use(cors());
expressApp.use(express.json());

expressApp.post("/mcp", async (req, res) => {
  const transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: undefined,
    enableJsonResponse: true,
  });
  const server = createServer();
  res.on("close", () => transport.close());
  await server.connect(transport);
  await transport.handleRequest(req, res, req.body);
});

expressApp.listen(PORT, (err) => {
  if (err) {
    console.error("Error starting server:", err);
    process.exit(1);
  }
  console.log(`etter MCP App server listening on http://localhost:${PORT}/mcp`);
  console.log(`Proxying tool calls to Python backend at ${PYTHON_API_URL}`);
});
