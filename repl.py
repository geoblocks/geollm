import os
import readline  # noqa: F401 - enables arrow history and Ctrl+R for input()

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from etter import GeoFilterParser

console = Console()


def print_result(result):
    """Pretty print the parsed query result."""
    loc = result.reference_location
    rel = result.spatial_relation
    conf = result.confidence_breakdown

    def row(key, value):
        table.add_row(f"[dim]{key}[/dim]", value)

    table = Table(box=box.SIMPLE, show_header=False, pad_edge=False, padding=(0, 1))
    table.add_column("Key", style="cyan", width=22)
    table.add_column("Value")

    # Query
    table.add_section()
    row("original query", f'[italic]"{result.original_query}"[/italic]')
    row("query type", result.query_type)

    # Location
    table.add_section()
    row("location name", f"[bold]{loc.name}[/bold]")
    type_str = loc.type or "[dim](not specified)[/dim]"
    if loc.type and loc.type_confidence is not None:
        type_str += f"  [dim]{loc.type_confidence:.2f}[/dim]"
    row("location type", type_str)

    # Spatial relation
    table.add_section()
    row("relation", f"[bold]{rel.relation}[/bold]")
    row("category", rel.category)
    if rel.explicit_distance is not None:
        row("explicit distance", f"{rel.explicit_distance}m")

    # Buffer config
    if result.buffer_config:
        buf = result.buffer_config
        table.add_section()
        row("buffer distance", f"{buf.distance_m}m")
        row("buffer from", buf.buffer_from)
        row("ring only", str(buf.ring_only))
        row("side", str(buf.side) if buf.side else "[dim]none[/dim]")
        row("inferred", str(buf.inferred))

    # Confidence
    table.add_section()
    row("overall confidence", _confidence_bar(conf.overall))
    row("location confidence", _confidence_bar(conf.location_confidence))
    if conf.relation_confidence is not None:
        row("relation confidence", _confidence_bar(conf.relation_confidence))
    if conf.reasoning:
        row("reasoning", f"[dim]{conf.reasoning}[/dim]")

    console.print(Panel(table, title="[bold green]Result[/bold green]", border_style="green"))


def _confidence_bar(value: float) -> str:
    filled = int(value * 10)
    bar = "█" * filled + "░" * (10 - filled)
    color = "green" if value >= 0.7 else "yellow" if value >= 0.4 else "red"
    return f"[{color}]{bar}[/{color}] {value:.2f}"


def main():
    """Run the interactive REPL."""
    load_dotenv()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        console.print("[bold red]Error:[/bold red] OPENAI_API_KEY environment variable not set")
        console.print("  Set it with: [dim]export OPENAI_API_KEY='sk-...'[/dim]")
        return

    with console.status("[bold blue]Initializing etter...[/bold blue]"):
        try:
            llm = init_chat_model(
                model="gpt-4o",
                model_provider="openai",
                temperature=0,
                api_key=api_key,
            )
        except Exception as e:
            console.print(f"[bold red]Failed to initialize LLM:[/bold red] {e}")
            return

        try:
            parser = GeoFilterParser(llm=llm, confidence_threshold=0.6, strict_mode=False)
        except Exception as e:
            console.print(f"[bold red]Failed to initialize parser:[/bold red] {e}")
            return

    console.print("[bold green]✓[/bold green] etter initialized successfully!\n")
    console.print(
        Panel(
            "Enter natural language geographic queries.\nType [bold]quit[/bold] to exit.",
            title="[bold]etter Interactive REPL[/bold]",
            border_style="blue",
        )
    )
    console.print()

    while True:
        try:
            query = input("\001\033[1;36m\002Query\001\033[0m\002: ").strip()

            if not query:
                continue

            if query.lower() in ("quit", "exit"):
                console.print("\n[bold]Goodbye![/bold]")
                break

            with console.status("[dim]Processing...[/dim]"):
                result = parser.parse(query)
            print_result(result)

        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold]Goodbye![/bold]")
            break
        except Exception as e:
            console.print(f"\n[bold red]Error:[/bold red] {e}\n")


if __name__ == "__main__":
    main()
