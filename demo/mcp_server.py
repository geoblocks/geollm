import os
from typing import Any

from dotenv import load_dotenv
from fastapi import HTTPException
from langchain_openai import ChatOpenAI
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel

from geollm.datasources import SwissNames3DSource
from geollm.parser import GeoFilterParser
from geollm.spatial import apply_spatial_relation

mcp = FastMCP("GeoLLM MCP Server")

load_dotenv()

# Data source configuration
SWISSNAMES3D_PATH = os.getenv("SWISSNAMES3D_PATH", "data")

if not os.path.exists(SWISSNAMES3D_PATH):
    raise RuntimeError(
        f"SwissNames3D data not found at {SWISSNAMES3D_PATH}. Please set SWISSNAMES3D_PATH environment variable."
    )

datasource = SwissNames3DSource(SWISSNAMES3D_PATH)

# Initialize GeoLLM components
llm = ChatOpenAI(model="gpt-4o", temperature=0)
parser = GeoFilterParser(llm, datasource=datasource)


class QueryResponse(BaseModel):
    query: str
    geo_query: dict[str, Any]  # The parsed GeoQuery
    result: dict[str, Any]  # GeoJSON FeatureCollection


@mcp.tool()
async def parse_geo_query(user_query: str) -> QueryResponse:
    """
    Transforms natural language location queries into structured geographic filters that can be used by search engines and spatial databases

    Args:
        user_query (str): The natural language query describing the geographic filter, e.g. "Find all locations within walking distance from Zurich main railway station"
    """
    try:
        geo_query = parser.parse(user_query)

        location_name = geo_query.reference_location.name
        features = datasource.search(location_name, type=geo_query.reference_location.type)

        if not features:
            raise ToolError(f"No features found for reference location '{location_name}'")

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

    except Exception as e:
        raise ToolError(f"Error processing query: {str(e)}") from e


def main():
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
