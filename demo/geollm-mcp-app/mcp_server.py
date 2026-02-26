import json
import os
from typing import Any

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.utilities.logging import get_logger
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from geollm.datasources import SwissNames3DSource
from geollm.parser import GeoFilterParser
from geollm.spatial import apply_spatial_relation

mcp = FastMCP("GeoLLM MCP Server")

logger = get_logger("GeoLLM")


class MCPRequestLogger(BaseHTTPMiddleware):
    """Log MCP requests to help debug client capabilities and message flow."""

    async def dispatch(self, request: Request, call_next):
        body = await request.body()
        try:
            payload = json.loads(body)
            method = payload.get("method", "")
            if method:
                if method == "initialize":
                    client_caps = payload.get("params", {}).get("capabilities", {})
                    logger.info(f"[MCP] initialize — client capabilities: {json.dumps(client_caps)}")
                else:
                    logger.info(f"[MCP] {method}")
        except Exception:
            pass

        # Rebuild the request with the already-consumed body
        async def receive() -> dict:
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(request.scope, receive)
        return await call_next(request)


load_dotenv()

SWISSNAMES3D_PATH = os.getenv("SWISSNAMES3D_PATH", "data")
RESSOURCE_URI = "ui://parse_geo_query/mcp-app.html"
# Must match the RESOURCE_MIME_TYPE constant in @modelcontextprotocol/ext-apps
# Hosts use this specific MIME type to identify MCP App resources
RESOURCE_MIME_TYPE = "text/html;profile=mcp-app"

if not os.path.exists(SWISSNAMES3D_PATH):
    raise RuntimeError(
        f"SwissNames3D data not found at {SWISSNAMES3D_PATH}. Please set SWISSNAMES3D_PATH environment variable."
    )

datasource = SwissNames3DSource(SWISSNAMES3D_PATH)

llm = ChatOpenAI(model="gpt-4o", temperature=0)
parser = GeoFilterParser(llm, datasource=datasource)


class QueryResponse(BaseModel):
    query: str
    geo_query: dict[str, Any]  # The parsed GeoQuery
    result: dict[str, Any]  # GeoJSON FeatureCollection


async def _run_geo_query(user_query: str) -> QueryResponse:
    """Shared implementation used by both the MCP tool and the REST endpoint."""
    geo_query = parser.parse(user_query)

    location_name = geo_query.reference_location.name
    features = datasource.search(location_name, type=geo_query.reference_location.type)

    if not features:
        raise ValueError(f"No features found for reference location '{location_name}'")

    result_features = []

    for i, reference_feature in enumerate(features):
        search_area = apply_spatial_relation(
            reference_feature["geometry"], geo_query.spatial_relation, geo_query.buffer_config
        )

        result_features.append(
            {
                "type": "Feature",
                "geometry": search_area,
                "properties": {
                    "role": "search_area",
                    "relation": geo_query.spatial_relation.relation,
                    "reference_index": i,
                    "reference_name": reference_feature["properties"]["name"],
                },
            }
        )

        result_features.append(reference_feature)

    feature_collection = {
        "type": "FeatureCollection",
        "features": result_features,
    }

    return QueryResponse(query=user_query, geo_query=geo_query.model_dump(), result=feature_collection)


@mcp.tool(meta={"ui": {"resourceUri": RESSOURCE_URI}, "ui/resourceUri": RESSOURCE_URI})
async def parse_geo_query(user_query: str) -> QueryResponse:
    """
    Transforms natural language location queries into structured geographic filters that can be used by search engines and spatial databases

    Args:
        user_query (str): The natural language query describing the geographic filter, e.g. "Find all locations within walking distance from Zurich main railway station"
    """
    logger.info(f"Received query: {user_query}")
    try:
        return await _run_geo_query(user_query)
    except Exception as e:
        raise ToolError(f"Error processing query: {str(e)}") from e


@mcp.custom_route("/api/parse_geo_query", methods=["POST"])
async def rest_parse_geo_query(request: Request) -> JSONResponse:
    """REST endpoint for the TypeScript MCP proxy server."""
    try:
        body = await request.json()
        user_query = body.get("user_query", "")
        if not user_query:
            return JSONResponse({"error": "user_query is required"}, status_code=400)
        logger.info(f"[REST] Received query: {user_query}")
        result = await _run_geo_query(user_query)
        return JSONResponse(result.model_dump())
    except Exception as e:
        logger.exception(f"[REST] Error: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@mcp.resource(uri=RESSOURCE_URI, mime_type=RESOURCE_MIME_TYPE)
async def map_resource() -> str:
    html_path = os.path.join(os.path.dirname(__file__), "dist", "mcp-app.html")
    with open(html_path) as f:
        return f.read()


def main():
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    app = mcp.streamable_http_app()
    app.add_middleware(MCPRequestLogger)
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
