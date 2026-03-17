import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from etter import GeoFilterParser


def print_result(result):
    """Pretty print the parsed query result."""
    print()
    print("=" * 60)
    print("RESULT")
    print("=" * 60)

    # Reference location
    print(f"\n📍 Location: {result.reference_location.name}")
    if result.reference_location.type:
        type_str = result.reference_location.type
        if result.reference_location.type_confidence is not None:
            type_str += f" (confidence: {result.reference_location.type_confidence:.2f})"
        print(f"   Type: {type_str}")
    else:
        print("   Type: (not specified)")

    # Spatial relation
    print(f"\n🔗 Spatial Relation: {result.spatial_relation.relation} ({result.spatial_relation.category})")

    # Buffer config (if any)
    if result.buffer_config:
        print(f"\n📏 Buffer Distance: {result.buffer_config.distance_m}m")
        print(f"   From: {result.buffer_config.buffer_from}")

    # Confidence breakdown
    print("\n📊 Confidence Scores:")
    print(f"   Overall: {result.confidence_breakdown.overall:.2f}")
    print(f"   Location: {result.confidence_breakdown.location_confidence:.2f}")
    if result.confidence_breakdown.relation_confidence:
        print(f"   Relation: {result.confidence_breakdown.relation_confidence:.2f}")

    print()


def main():
    """Run the interactive REPL."""
    # Load environment variables
    load_dotenv()

    # Get API key from environment
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("   Set it with: export OPENAI_API_KEY='sk-...'")
        return

    # Initialize LLM
    print("🔄 Initializing etter...")
    try:
        llm = init_chat_model(
            model="gpt-4o",
            model_provider="openai",
            temperature=0,  # Deterministic for parsing
            api_key=api_key,
        )
    except Exception as e:
        print(f"❌ Failed to initialize LLM: {e}")
        return

    # Initialize parser
    try:
        parser = GeoFilterParser(llm=llm, confidence_threshold=0.6, strict_mode=False)
    except Exception as e:
        print(f"❌ Failed to initialize parser: {e}")
        return

    print("✅ etter initialized successfully!")
    print()
    print("=" * 60)
    print("etter Interactive REPL")
    print("=" * 60)
    print("Enter natural language geographic queries.")
    print("Type 'help' for available commands or 'quit' to exit.")
    print()

    while True:
        try:
            # Get user input
            query = input("🔍 Query: ").strip()

            if not query:
                continue

            # Handle special commands
            if query.lower() == "quit" or query.lower() == "exit":
                print("👋 Goodbye!")
                break

            if query.lower() == "help":
                print()
                print("Available commands:")
                print("  help    - Show this help message")
                print("  quit    - Exit the REPL")
                print("  relations - List available spatial relations")
                print()
                print("Example queries:")
                print("  - 'in Bern'")
                print("  - 'near Lake Geneva'")
                print("  - 'north of Zurich'")
                print("  - 'Bushaltestellen in Zürich' (German)")
                print()
                continue

            if query.lower() == "relations":
                print()
                print("Available Spatial Relations:")
                print("=" * 60)
                print("Containment:", ", ".join(parser.get_available_relations("containment")))
                print("Buffer:", ", ".join(parser.get_available_relations("buffer")))
                print("Directional:", ", ".join(parser.get_available_relations("directional")))
                print()
                continue

            # Parse the query
            print("⏳ Processing...")
            result = parser.parse(query)
            print_result(result)

        except KeyboardInterrupt:
            print("\n👋 Interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print()


if __name__ == "__main__":
    main()
