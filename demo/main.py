import contextlib
import json
import logging
import os
import time
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain.chat_models import init_chat_model
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel

from etter.datasources import CompositeDataSource, IGNBDCartoSource, PostGISDataSource, SwissNames3DSource
from etter.datasources.ign_bdcarto import IGN_BDCARTO_TYPE_MAP
from etter.datasources.swissnames3d import OBJEKTART_TYPE_MAP
from etter.parser import GeoFilterParser
from etter.spatial import apply_spatial_relation

# Load environment variables
load_dotenv()

logger = logging.getLogger("uvicorn")

geo_mcp = FastMCP("etter MCP Server", stateless_http=True, json_response=True)


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    async with geo_mcp.session_manager.run():
        yield


app = FastAPI(title="etter Demo", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data source configuration
#
# When ETTER_DB_URL is set the demo uses PostGISDataSource (DB-backed).
# Otherwise it falls back to the original file-based sources (SwissNames3D
# shapefiles and IGN BD-CARTO GeoPackages).

ETTER_DB_URL = os.getenv("ETTER_DB_URL")

sources = []

if ETTER_DB_URL:
    SWISSNAMES3D_TABLE = os.getenv("SWISSNAMES3D_TABLE", "swissnames3d")
    IGN_BDCARTO_TABLE = os.getenv("IGN_BDCARTO_TABLE", "ign_bdcarto")
    DB_SCHEMA = os.getenv("DB_SCHEMA", "public")

    swissnames_table = f"{DB_SCHEMA}.{SWISSNAMES3D_TABLE}"
    sources.append(
        PostGISDataSource(
            connection=ETTER_DB_URL,
            table=swissnames_table,
            type_map=OBJEKTART_TYPE_MAP,
        )
    )

    bdcarto_table = f"{DB_SCHEMA}.{IGN_BDCARTO_TABLE}"
    sources.append(
        PostGISDataSource(
            connection=ETTER_DB_URL,
            table=bdcarto_table,
            type_map=IGN_BDCARTO_TYPE_MAP,
        )
    )
else:
    SWISSNAMES3D_PATH = os.getenv("SWISSNAMES3D_PATH", "data")
    IGN_BDCARTO_PATH = os.getenv("IGN_BDCARTO_PATH", "data/bdcarto")

    if not os.path.exists(SWISSNAMES3D_PATH):
        raise RuntimeError(
            f"SwissNames3D data not found at {SWISSNAMES3D_PATH}. "
            "Set SWISSNAMES3D_PATH or provide ETTER_DB_URL for PostGIS mode."
        )

    sources.append(SwissNames3DSource(SWISSNAMES3D_PATH))

    if os.path.exists(IGN_BDCARTO_PATH):
        try:
            ign_source = IGNBDCartoSource(IGN_BDCARTO_PATH)
            ign_source.get_available_types()
            sources.append(ign_source)
        except ValueError as e:
            logger.warning("IGN BD-CARTO not loaded: %s", e)
    else:
        logger.warning("IGN BD-CARTO path not found (%s), skipping.", IGN_BDCARTO_PATH)

datasource = CompositeDataSource(*sources)

# Initialize etter components
LLM_API_KEY = os.getenv("LLM_API_KEY")
if not LLM_API_KEY:
    raise RuntimeError("LLM_API_KEY not set. Please set it in your .env file.")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o")
if not LLM_MODEL:
    raise RuntimeError("LLM_MODEL not set. Please set it in your .env file.")
llm = init_chat_model(model=LLM_MODEL, temperature=0, api_key=LLM_API_KEY)
parser = GeoFilterParser(llm, datasource=datasource)


def _build_result_features(geo_query, reference_features: list) -> list:
    """Apply spatial relations and return a flat list of (search_area, reference) Feature dicts."""
    result_features = []
    for i, reference_feature in enumerate(reference_features):
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
    return result_features


async def _run_geo_query(query: str) -> "QueryResponse":
    """Parse a natural-language query and resolve it to a QueryResponse.

    Raises:
        ValueError: if the reference location is not found in the datasource.
    """
    geo_query = await parser.aparse(query)
    location_name = geo_query.reference_location.name
    features = datasource.search(location_name, type=geo_query.reference_location.type)
    if not features:
        raise ValueError(f"Location '{location_name}' not found")
    result_features = _build_result_features(geo_query, features)
    feature_collection = {"type": "FeatureCollection", "features": result_features}
    return QueryResponse(query=query, geo_query=geo_query.model_dump(), result=feature_collection)


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    query: str
    geo_query: dict[str, Any]  # The parsed GeoQuery
    result: dict[str, Any]  # GeoJSON FeatureCollection


@app.post("/api/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    try:
        return await _run_geo_query(request.query)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Error processing query")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query/stream")
async def process_query_stream(request: QueryRequest):
    """
    Stream processing of a geographic query with real-time reasoning and results.

    Returns Server-Sent Events (SSE) with two event types:
    - reasoning: Intermediate processing steps from the LLM
    - data-response: Final GeoQuery result and feature collection

    Example usage:
        curl -X POST http://localhost:8000/api/query/stream \
             -H "Content-Type: application/json" \
             -d '{"query":"restaurants near Lake Geneva"}' \
             --no-buffer
    """

    async def event_generator():
        try:
            geo_query_result = None

            # Stream parsing events
            parse_start = time.perf_counter()
            async for event in parser.parse_stream(request.query):
                yield f"data: {json.dumps(event)}\n\n"

                if event["type"] == "data-response":
                    geo_query_result = event["content"]
            yield f"data: {json.dumps({'type': 'reasoning', 'content': 'LLM parsing', 'duration_ms': (time.perf_counter() - parse_start) * 1000})}\n\n"

            if geo_query_result:
                yield f"data: {json.dumps({'type': 'reasoning', 'content': 'Resolving location in database'})}\n\n"

                from etter.models import GeoQuery

                geo_query = GeoQuery.model_validate(geo_query_result)

                location_name = geo_query.reference_location.name
                search_start = time.perf_counter()
                logger.info(
                    f"Searching for location: {location_name} with type hint: {geo_query.reference_location.type}"
                )
                features = datasource.search(location_name, type=geo_query.reference_location.type)
                logger.info(
                    f"Found {len(features)} features for location '{location_name}' in {time.perf_counter() - search_start:.2f} seconds"
                )
                logger.info(f"Features properties: {[f['properties'] for f in features]}")

                if not features:
                    yield f"data: {json.dumps({'type': 'reasoning', 'content': f'Location not found: {location_name}'})}\n\n"
                    yield f"data: {json.dumps({'type': 'error', 'content': f'Location not found: {location_name}'})}\n\n"
                    return

                yield f"data: {json.dumps({'type': 'reasoning', 'content': f'Found {len(features)} matching location(s)', 'duration_ms': (time.perf_counter() - search_start) * 1000})}\n\n"

                yield f"data: {json.dumps({'type': 'reasoning', 'content': 'Computing spatial search areas'})}\n\n"

                spatial_start = time.perf_counter()
                result_features = _build_result_features(geo_query, features)
                spatial_duration = (time.perf_counter() - spatial_start) * 1000
                yield f"data: {json.dumps({'type': 'reasoning', 'content': 'Computed spatial relations', 'duration_ms': spatial_duration})}\n\n"

                feature_collection = {
                    "type": "FeatureCollection",
                    "features": result_features,
                }

                final_response = {
                    "query": request.query,
                    "geo_query": geo_query_result,
                    "result": feature_collection,
                }

                yield f"data: {json.dumps({'type': 'reasoning', 'content': 'Query processing completed'})}\n\n"
                yield f"data: {json.dumps({'type': 'result', 'content': final_response})}\n\n"
                yield f"data: {json.dumps({'type': 'finish'})}\n\n"

        except Exception as e:
            error_msg = f"Error during streaming: {str(e)}"
            logger.exception("Error during streaming")
            yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@geo_mcp.tool()
async def parse_geo_query(user_query: str) -> dict[str, Any]:
    """
    Transforms natural language location queries into structured geographic filters
    that can be used by search engines and spatial databases.

    Args:
        user_query: The natural language query describing the geographic filter,
            e.g. "Find all locations within walking distance from Zurich main railway station"
    """
    try:
        return (await _run_geo_query(user_query)).model_dump()
    except ValueError as e:
        raise ToolError(str(e))


# Mount MCP server (streamable_http_path="/" so endpoint is /mcp, not /mcp/mcp)
geo_mcp.settings.streamable_http_path = "/"
app.mount("/mcp", geo_mcp.streamable_http_app())

# Mount static files (must be last)
app.mount("/", StaticFiles(directory="demo/static", html=True), name="static")
