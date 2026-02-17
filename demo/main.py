import json
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from geollm.datasources import SwissNames3DSource
from geollm.parser import GeoFilterParser
from geollm.spatial import apply_spatial_relation

app = FastAPI(title="GeoLLM Demo")

# Load environment variables
load_dotenv()

# Enable CORS (for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Data source configuration
SWISSNAMES3D_PATH = os.getenv("SWISSNAMES3D_PATH", "data")

if not os.path.exists(SWISSNAMES3D_PATH):
    raise RuntimeError(
        f"SwissNames3D data not found at {SWISSNAMES3D_PATH}. Please set SWISSNAMES3D_PATH environment variable."
    )

print(f"Loading SwissNames3D from {SWISSNAMES3D_PATH}...")
datasource = SwissNames3DSource(SWISSNAMES3D_PATH)

# Initialize GeoLLM components
llm = ChatOpenAI(model="gpt-4o", temperature=0)
parser = GeoFilterParser(llm, datasource=datasource)


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    query: str
    geo_query: dict[str, Any]  # The parsed GeoQuery
    result: dict[str, Any]  # GeoJSON FeatureCollection


@app.post("/api/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    try:
        # 1. Parse query
        geo_query = parser.parse(request.query)

        # 2. Resolve location
        location_name = geo_query.reference_location.name
        features = datasource.search(location_name, type=geo_query.reference_location.type)

        if not features:
            raise HTTPException(status_code=404, detail=f"Location '{location_name}' not found")

        # 3. Apply spatial relation to ALL matching features
        result_features = []

        for i, reference_feature in enumerate(features):
            # Apply spatial relation to this feature
            search_area = apply_spatial_relation(
                reference_feature["geometry"], geo_query.spatial_relation, geo_query.buffer_config
            )

            # Add search area feature
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

            # Add reference feature
            result_features.append(reference_feature)

        # 4. Construct response FeatureCollection with all features and search areas
        feature_collection = {
            "type": "FeatureCollection",
            "features": result_features,
        }

        return QueryResponse(query=request.query, geo_query=geo_query.model_dump(), result=feature_collection)

    except Exception as e:
        print(f"Error processing query: {e}")
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
            async for event in parser.parse_stream(request.query):
                # Forward all events from parser
                yield f"data: {json.dumps(event)}\n\n"

                # Capture the final GeoQuery for spatial processing
                if event["type"] == "data-response":
                    geo_query_result = event["content"]

            # If we have a parsed query, process the spatial relations
            if geo_query_result:
                yield f"data: {json.dumps({'type': 'reasoning', 'content': 'Resolving location in database'})}\n\n"

                # Reconstruct GeoQuery from dict (for type safety)
                from geollm.models import GeoQuery

                geo_query = GeoQuery.model_validate(geo_query_result)

                # Resolve location
                location_name = geo_query.reference_location.name
                features = datasource.search(location_name, type=geo_query.reference_location.type)

                if not features:
                    yield f"data: {json.dumps({'type': 'reasoning', 'content': f'Location not found: {location_name}'})}\n\n"
                    yield f"data: {json.dumps({'type': 'error', 'content': f'Location not found: {location_name}'})}\n\n"
                    return

                yield f"data: {json.dumps({'type': 'reasoning', 'content': f'Found {len(features)} matching location(s)'})}\n\n"

                # Apply spatial relation to ALL matching features
                yield f"data: {json.dumps({'type': 'reasoning', 'content': 'Computing spatial search areas'})}\n\n"

                result_features = []

                for i, reference_feature in enumerate(features):
                    # Apply spatial relation to this feature
                    search_area = apply_spatial_relation(
                        reference_feature["geometry"], geo_query.spatial_relation, geo_query.buffer_config
                    )

                    # Add search area feature
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

                    # Add reference feature
                    result_features.append(reference_feature)

                # Construct final response
                feature_collection = {
                    "type": "FeatureCollection",
                    "features": result_features,
                }

                # Send final result
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
            print(error_msg)
            yield f"data: {json.dumps({'type': 'error', 'content': error_msg})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# Mount static files (must be last)
app.mount("/", StaticFiles(directory="demo/static", html=True), name="static")
