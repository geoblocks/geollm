"""
Main parser class for natural language geographic query parsing.
"""

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Literal

from langchain_core.language_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate

from .exceptions import ParsingError
from .models import GeoQuery
from .prompts import build_prompt_template
from .spatial_config import SpatialRelationConfig
from .validators import validate_query

if TYPE_CHECKING:
    from .datasources.protocol import GeoDataSource


class GeoFilterParser:
    """
    Main entry point for parsing natural language location queries.

    This class orchestrates the entire parsing pipeline:
    1. Initialize LLM with structured output
    2. Build prompt with spatial relations and examples
    3. Parse query through LLM
    4. Validate and enrich with defaults
    5. Return structured GeoQuery

    Examples:
        Basic usage:
        >>> from langchain.chat_models import init_chat_model
        >>> llm = init_chat_model(model="gpt-4o", model_provider="openai", api_key="sk-...")
        >>> parser = GeoFilterParser(llm=llm)
        >>> result = parser.parse("restaurants in Lausanne")
        >>> print(result.reference_location.name)
        'Lausanne'

        With strict confidence mode:
        >>> parser = GeoFilterParser(llm=llm, confidence_threshold=0.8, strict_mode=True)
        >>> result = parser.parse("near the station")  # May raise LowConfidenceError
    """

    def __init__(
        self,
        llm: BaseChatModel,
        spatial_config: SpatialRelationConfig | None = None,
        confidence_threshold: float = 0.6,
        strict_mode: bool = False,
        include_examples: bool = True,
        datasource: "GeoDataSource | None" = None,
    ):
        """
        Initialize the parser.

        Args:
            llm: LangChain LLM instance (required).
            spatial_config: Spatial relation configuration. If None, uses defaults
            confidence_threshold: Minimum confidence to accept (0-1)
            strict_mode: If True, raise error on low confidence. If False, warn only
            include_examples: Whether to include few-shot examples in prompt
            datasource: Optional GeoDataSource instance. If provided, the LLM will be informed
                       about the concrete types available in that datasource for better type inference.

        Example:
            >>> from langchain.chat_models import init_chat_model
            >>> from geollm.datasources.swissnames3d import SwissNames3DSource
            >>> llm = init_chat_model(model="gpt-4o", model_provider="openai", temperature=0)
            >>> datasource = SwissNames3DSource("data/")
            >>> parser = GeoFilterParser(llm=llm, datasource=datasource)
        """
        self.llm = llm

        # Initialize spatial config
        self.spatial_config = spatial_config or SpatialRelationConfig()

        # Settings
        self.confidence_threshold = confidence_threshold
        self.strict_mode = strict_mode
        self.include_examples = include_examples
        self.datasource = datasource

        # Build structured LLM
        self.structured_llm = self._build_structured_llm()

        # Build prompt template
        self.prompt = self._build_prompt()

    def _build_structured_llm(self):
        """Create LLM with structured output using Pydantic model."""

        return self.llm.with_structured_output(
            GeoQuery,
            method="function_calling",  # Use function_calling for broader schema support
            include_raw=True,  # For error debugging
        )

    def _build_prompt(self) -> ChatPromptTemplate:
        """Build prompt template with spatial relations, examples, and available types."""
        available_types = None
        if self.datasource is not None:
            available_types = self.datasource.get_available_types()

        return build_prompt_template(
            spatial_config=self.spatial_config,
            include_examples=self.include_examples,
            available_types=available_types,
        )

    def parse(self, query: str) -> GeoQuery:
        """
        Parse a natural language location query into structured format.

        This is the main method for parsing queries. It:
        1. Invokes the LLM with structured output
        2. Validates the spatial relation is registered
        3. Enriches with default parameters
        4. Checks confidence threshold

        Args:
            query: Natural language query in any language

        Returns:
            GeoQuery: Structured query representation with confidence scores

        Raises:
            ParsingError: If LLM fails to parse query into valid structure
            ValidationError: If parsed query fails business logic validation
            UnknownRelationError: If spatial relation is not registered
            LowConfidenceError: If confidence below threshold (strict mode only)

        Warns:
            LowConfidenceWarning: If confidence below threshold (permissive mode)

        Examples:
            Simple containment query:
            >>> result = parser.parse("in Bern")
            >>> result.reference_location.name
            'Bern'
            >>> result.spatial_relation.relation
            'in'

            Buffer query:
            >>> result = parser.parse("near Lake Geneva")
            >>> result.spatial_relation.relation
            'near'
            >>> result.buffer_config.distance_m
            5000

            Directional query:
            >>> result = parser.parse("north of Lausanne")
            >>> result.spatial_relation.relation
            'north_of'
            >>> result.reference_location.name
            'Lausanne'

            Multilingual:
            >>> result = parser.parse("près de Genève")
            >>> result.spatial_relation.relation
            'near'
            >>> result.reference_location.name
            'Genève'
        """
        # Format prompt with query
        formatted_messages = self.prompt.format_messages(query=query)

        # Invoke LLM with structured output
        try:
            response = self.structured_llm.invoke(formatted_messages)
        except Exception as e:
            raise ParsingError(
                message=f"LLM invocation failed: {str(e)}",
                raw_response="",
                original_error=e,
            ) from e

        # Check for parsing errors
        parsed = response.get("parsed") if isinstance(response, dict) else response

        if parsed is None:
            raw = response.get("raw", "") if isinstance(response, dict) else ""
            error = response.get("parsing_error") if isinstance(response, dict) else None
            raise ParsingError(
                message="Failed to parse query into structured format. "
                "LLM may have returned invalid JSON or missed required fields.",
                raw_response=str(raw),
                original_error=error,
            )

        geo_query = parsed
        assert isinstance(geo_query, GeoQuery), "Parsed result must be GeoQuery"

        # Ensure original_query is set correctly
        if not geo_query.original_query or geo_query.original_query != query:
            geo_query.original_query = query

        # Run validation pipeline
        geo_query = validate_query(
            geo_query,
            self.spatial_config,
            confidence_threshold=self.confidence_threshold,
            strict_mode=self.strict_mode,
        )

        return geo_query

    async def parse_stream(self, query: str) -> AsyncGenerator[dict]:
        """
        Parse a natural language location query with streaming reasoning and results.

        This method provides real-time feedback during the parsing process by yielding
        intermediate reasoning steps and the final GeoQuery result. This is useful for
        providing users with transparency into the LLM's decision-making process and
        for building responsive UIs.

        The stream yields dictionaries with the following event types:
        - {"type": "start"} - Stream started
        - {"type": "reasoning", "content": str} - Intermediate processing steps
        - {"type": "data-response", "content": dict} - Final GeoQuery as JSON
        - {"type": "error", "content": str} - Errors encountered during processing
        - {"type": "finish"} - Stream completed successfully

        Args:
            query: Natural language query in any language

        Yields:
            dict: Stream events with type and optional content fields

        Raises:
            ParsingError: If LLM fails to parse query into valid structure
            ValidationError: If parsed query fails business logic validation
            UnknownRelationError: If spatial relation is not registered
            LowConfidenceError: If confidence below threshold (strict mode only)

        Examples:
            Basic usage with async iteration:
            >>> async for event in parser.parse_stream("restaurants near Lake Geneva"):
            ...     if event["type"] == "reasoning":
            ...         print(f"Reasoning: {event['content']}")
            ...     elif event["type"] == "data-response":
            ...         geo_query = event["content"]
            ...         print(f"Location: {geo_query['reference_location']['name']}")
            ...     elif event["type"] == "error":
            ...         print(f"Error: {event['content']}")

            Using in a FastAPI streaming endpoint:
            >>> from fastapi.responses import StreamingResponse
            >>> @app.get("/stream")
            >>> async def stream_endpoint(q: str):
            ...     async def event_stream():
            ...         async for event in parser.parse_stream(q):
            ...             yield f"data: {json.dumps(event)}\\n\\n"
            ...     return StreamingResponse(event_stream(), media_type="text/event-stream")
        """
        try:
            # Signal start of stream
            yield {"type": "start"}

            yield {"type": "reasoning", "content": "Preparing query for LLM processing"}
            formatted_messages = self.prompt.format_messages(query=query)

            yield {"type": "reasoning", "content": "Analyzing spatial relationship and location"}
            try:
                response = self.structured_llm.invoke(formatted_messages)
            except Exception as e:
                yield {"type": "error", "content": f"LLM invocation failed: {str(e)}"}
                raise ParsingError(
                    message=f"LLM invocation failed: {str(e)}",
                    raw_response="",
                    original_error=e,
                ) from e

            yield {"type": "reasoning", "content": "Parsing LLM response into structured format"}
            parsed = response.get("parsed") if isinstance(response, dict) else response

            if parsed is None:
                raw = response.get("raw", "") if isinstance(response, dict) else ""
                error = response.get("parsing_error") if isinstance(response, dict) else None
                yield {"type": "error", "content": "Failed to parse response - invalid JSON or missing fields"}
                raise ParsingError(
                    message="Failed to parse query into structured format. "
                    "LLM may have returned invalid JSON or missed required fields.",
                    raw_response=str(raw),
                    original_error=error,
                )

            geo_query = parsed
            assert isinstance(geo_query, GeoQuery), "Parsed result must be GeoQuery"

            # Ensure original_query is set correctly
            if not geo_query.original_query or geo_query.original_query != query:
                geo_query.original_query = query

            if geo_query.confidence_breakdown.reasoning:
                yield {
                    "type": "reasoning",
                    "content": f"LLM reasoning: {geo_query.confidence_breakdown.reasoning}",
                }

            yield {"type": "reasoning", "content": "Validating spatial relation configuration"}
            geo_query = validate_query(
                geo_query,
                self.spatial_config,
                confidence_threshold=self.confidence_threshold,
                strict_mode=self.strict_mode,
            )

            yield {"type": "reasoning", "content": "Query parsing completed successfully"}
            yield {"type": "data-response", "content": geo_query.model_dump()}

            # Signal successful completion
            yield {"type": "finish"}

        except Exception as e:
            # Emit error event before re-raising
            yield {"type": "error", "content": f"Error during parsing: {str(e)}"}
            raise

    def parse_batch(self, queries: list[str]) -> list[GeoQuery]:
        """
        Parse multiple queries in batch.

        Note: This is a simple sequential implementation.
        For true parallelization, consider using async methods or ThreadPoolExecutor.

        Args:
            queries: List of natural language queries

        Returns:
            List of GeoQuery objects (same order as input)

        Raises:
            Same exceptions as parse() for any failing query
        """
        return [self.parse(query) for query in queries]

    def get_available_relations(
        self, category: Literal["containment", "buffer", "directional"] | None = None
    ) -> list[str]:
        """
        Get list of available spatial relations.

        Args:
            category: Optional filter by category ("containment", "buffer", "directional")

        Returns:
            List of relation names
        """
        return self.spatial_config.list_relations(category=category)

    def describe_relation(self, relation_name: str) -> str:
        """
        Get description of a spatial relation.

        Args:
            relation_name: Name of the relation

        Returns:
            Human-readable description

        Raises:
            UnknownRelationError: If relation is not registered
        """
        config = self.spatial_config.get_config(relation_name)
        return config.description
