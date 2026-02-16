import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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


# Mount static files (must be last)
app.mount("/", StaticFiles(directory="demo/static", html=True), name="static")
