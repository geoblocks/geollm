# GeoLLM

Natural language geographic query parsing using LLMs.

## Overview

GeoLLM transforms natural language location queries into structured geographic filters that can be used by search engines and spatial databases.
It uses Large Language Models (LLMs) to understand multilingual queries and extract spatial relationships.

**Key Principle:** GeoLLM's sole purpose is to extract the **geographic filter** from user queries. It does NOT handle feature/activity identification or search execution.

## Features

- **Geographic Filters Only**: Extracts spatial relationships from queries, ignoring non-geographic content
- **Multilingual Support**: Parse queries in English, German, French, Italian, and more
- **Rich Spatial Relations**: Support for containment, buffer, and directional queries
- **Structured Output**: Pydantic models with full type safety
- **Streaming Support**: Real-time feedback with reasoning transparency for responsive UIs
- **Flexible Configuration**: Customizable spatial relations and confidence thresholds
- **LLM Provider Agnostic**: Works with OpenAI, Anthropic, or local models

## What GeoLLM Does (and Doesn't Do)

**✅ GeoLLM extracts:**

- Spatial relations: "north of", "in", "near", etc.
- Reference locations: "Lausanne", "Lake Geneva", etc.
- Distance parameters: "within 5km", "around 2 miles", etc.

**❌ GeoLLM does NOT handle:**

- Feature/activity identification: "hiking", "restaurants", "hotels"
- Attribute filtering: "with children", "vegetarian", "4-star"
- Search execution or database queries

**Integration Pattern:**
Parent application handles feature/activity filtering and combines it with GeoLLM's geographic filter for complete search functionality.

## Installation

This project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
# Install dependencies
uv sync

# Or with development dependencies
uv sync --extra dev
```

## REPL

An interactive REPL is available for testing queries interactively:

Set your OpenAI API key before running:

```bash
export OPENAI_API_KEY='sk-...'
uv run python repl.py
```

## Demo API Server

A FastAPI demo server is available that combines query parsing with geographic resolution using SwissNames3D data.

**Setup:**

Set `OPENAI_API_KEY` in your `.env` file:

```bash
echo "OPENAI_API_KEY=sk-..." > .env
```

**Running the server:**

```bash
uv run fastapi dev demo/main.py
```

The API will be available at `http://localhost:8000`.

**Making a query:**

```bash
# Standard endpoint (returns complete result)
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "north of Lausanne"}'

# Streaming endpoint (returns Server-Sent Events)
curl -X POST http://localhost:8000/api/query/stream \
  -H "Content-Type: application/json" \
  -d '{"query": "north of Lausanne"}' \
  --no-buffer
```

Response: A GeoJSON FeatureCollection containing the parsed geographic query, spatial relation, and computed search areas.

The web UI at `http://localhost:8000` includes a toggle to enable streaming mode with real-time reasoning display.

## Quick Start

```python
from langchain_openai import ChatOpenAI
from geollm import GeoFilterParser
import os

# Initialize LLM
llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    api_key=os.getenv("OPENAI_API_KEY")
)

# Initialize parser
parser = GeoFilterParser(
    llm=llm,
    confidence_threshold=0.6,
    strict_mode=False
)

# Strict mode - raises error on low confidence
parser = GeoFilterParser(
    llm=llm,
    confidence_threshold=0.8,
    strict_mode=True
)
```

### Custom Spatial Relations

```python
from geollm import SpatialRelationConfig, RelationConfig

config = SpatialRelationConfig()
config.register_relation(RelationConfig(
    name="close_to",
    category="buffer",
    description="Very close proximity",
    default_distance_m=1000,
    buffer_from="center"
))

parser = GeoFilterParser(spatial_config=config)
```

## API Reference

### GeoFilterParser

Main class for parsing queries.

**Methods:**

- `parse(query: str) -> GeoQuery`: Parse a single query
- `parse_stream(query: str) -> AsyncGenerator[dict]`: Parse with streaming events
- `parse_batch(queries: List[str]) -> List[GeoQuery]`: Parse multiple queries
- `get_available_relations(category: Optional[str]) -> List[str]`: List available relations
- `describe_relation(name: str) -> str`: Get relation description

### GeoQuery

Structured output model representing the parsed geographic filter.

**Attributes:**

- `query_type`: Type of query (simple, compound, split, boolean)
- `spatial_relation`: Spatial relationship (e.g., "north_of", "in", "near")
- `reference_location`: Reference location (e.g., "Lausanne")
- `buffer_config`: Buffer parameters (optional)
- `confidence_breakdown`: Confidence scores
- `original_query`: Original input text

**Note:** GeoLLM is fully implemented with three integrated layers: parsing, geographic resolution via datasources, and spatial operations. The demo API shows a complete end-to-end workflow that resolves locations and computes search areas.

## Available Spatial Relations

### Containment

- `in`: Exact boundary matching

### Buffer/Proximity

- `near`: Proximity with context-aware distance (default 5km, LLM infers based on activity, feature scale, and intent)
- `on_shores_of`: 1km ring buffer (excludes water body)
- `along`: 500m buffer for linear features
- `in_the_heart_of`: Erosion for central areas (default -500m, LLM infers based on area size)

### Directional

- **Cardinal**: `north_of`, `south_of`, `east_of`, `west_of`: 10km sector (90° each)
- **Diagonal**: `northeast_of`, `southeast_of`, `southwest_of`, `northwest_of`: 10km sector (90° each)

## Error Handling

```python
from geollm import ParsingError, UnknownRelationError, LowConfidenceError

try:
    result = parser.parse("some query")
except ParsingError as e:
    print(f"Failed to parse: {e}")
    print(f"Raw LLM response: {e.raw_response}")
except UnknownRelationError as e:
    print(f"Unknown relation: {e.relation_name}")
except LowConfidenceError as e:
    print(f"Low confidence: {e.confidence}")
    print(f"Reasoning: {e.reasoning}")
```

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system design.

## Development

```bash
# Install dev dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Format code
uv run ruff format geollm tests

# Type checking
uv run mypy geollm

# Linting
uv run ruff check geollm tests
```
