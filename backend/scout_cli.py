#!/usr/bin/env python3
"""AI Scout CLI — Rich terminal UI for researching compliance requirements.

Usage:
    python scout_cli.py --state MT --city Bozeman --county Gallatin
    python scout_cli.py --state CA --city "San Francisco" --county "San Francisco"
    python scout_cli.py --state MT  # statewide only
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

load_dotenv()

console = Console()


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------

BANNER_LINES = [
    r"       _    ___   _____                 __  ",
    r"      / \  |_ _| / ___| ___ ___  _   _| |_ ",
    r"     / _ \  | |  \___ \/ __/ _ \| | | | __|",
    r"    / ___ \ | |   ___) | (_| (_) | |_| | |_ ",
    r"   /_/   \_\___| |____/ \___\___/ \__,_|\__|",
]


def show_banner():
    """Display the AI Scout banner."""
    console.print()
    art_width = max(len(line) for line in BANNER_LINES)
    inner_width = console.width - 2 - 4
    pad = max(0, (inner_width - art_width) // 2)
    centered = [" " * pad + line.ljust(art_width) for line in BANNER_LINES]
    art = "\n".join(centered)
    console.print(
        Panel(
            Text(art, style="bold green", no_wrap=True),
            title="[bold white]JACE AI Scout[/]",
            subtitle="[dim]LLM-Powered Compliance Research[/]",
            border_style="green",
            padding=(1, 2),
        )
    )
    console.print()


# ---------------------------------------------------------------------------
# Result display
# ---------------------------------------------------------------------------

CATEGORY_ICONS = {
    "FORM": "\U0001f4c4",          # 📄
    "INSPECTION": "\U0001f50d",     # 🔍
    "DISCLOSURE": "\U0001f4e2",     # 📢
    "CERTIFICATE": "\U00002705",    # ✅
    "FEE": "\U0001f4b0",           # 💰
}


def _confidence_color(conf: float) -> str:
    if conf >= 0.9:
        return "bold green"
    if conf >= 0.7:
        return "yellow"
    if conf >= 0.5:
        return "dark_orange"
    return "red"


def show_results(result) -> None:
    """Pretty-print the scout result."""
    from scout_models import ScoutResult

    assert isinstance(result, ScoutResult)

    # Jurisdiction header
    console.print(
        Panel(
            f"[bold]{result.jurisdiction_key}[/bold]\n"
            f"Type: {result.jurisdiction_type}  |  "
            f"Requirements: {len(result.requirements)}  |  "
            f"Source: {result.source}  |  "
            f"Verified: {'Yes' if result.is_verified else '[yellow]No — needs review[/yellow]'}",
            title=f"[bold white]Results: {result.city or ''}"
                  f"{', ' + result.county + ' County' if result.county else ''}"
                  f", {result.state}[/]",
            border_style="cyan",
        )
    )

    if not result.requirements:
        console.print("  [dim]No requirements discovered.[/dim]")
        return

    # Requirements table
    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
        expand=True,
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Category", width=6, justify="center")
    table.add_column("Name", min_width=20)
    table.add_column("Code", width=14)
    table.add_column("Status", width=12)
    table.add_column("Confidence", width=10, justify="center")
    table.add_column("Authority", min_width=15)

    for i, req in enumerate(result.requirements, 1):
        icon = CATEGORY_ICONS.get(req.category.value, "")
        conf_str = f"{req.confidence:.0%}"
        conf_color = _confidence_color(req.confidence)

        status_colors = {
            "REQUIRED": "bold red",
            "LIKELY_REQUIRED": "yellow",
            "NOT_REQUIRED": "green",
            "UNKNOWN": "dim",
        }
        status_style = status_colors.get(req.status.value, "")

        table.add_row(
            str(i),
            icon,
            req.name,
            req.code or "[dim]—[/dim]",
            f"[{status_style}]{req.status.value}[/{status_style}]",
            f"[{conf_color}]{conf_str}[/{conf_color}]",
            req.authority or "[dim]—[/dim]",
        )

    console.print(table)

    # Detail panels for each requirement
    for i, req in enumerate(result.requirements, 1):
        icon = CATEGORY_ICONS.get(req.category.value, "")
        details = []
        details.append(f"[bold]Description:[/bold] {req.description}")
        if req.fee:
            details.append(f"[bold]Fee:[/bold] {req.fee}")
        if req.url:
            details.append(f"[bold]URL:[/bold] {req.url}")
        if req.notes:
            details.append(f"[bold]Notes:[/bold] {req.notes}")
        if req.source_reasoning:
            details.append(f"[dim]Reasoning: {req.source_reasoning}[/dim]")

        conf_color = _confidence_color(req.confidence)
        console.print(
            Panel(
                "\n".join(details),
                title=f"[bold]{icon} {i}. {req.name}[/] [{conf_color}]({req.confidence:.0%})[/]",
                border_style="dim",
            )
        )

    # Summary
    avg_conf = sum(r.confidence for r in result.requirements) / len(result.requirements)
    console.print(
        f"\n  [bold green]Scout complete:[/] "
        f"{len(result.requirements)} requirements discovered  |  "
        f"Avg confidence: [{_confidence_color(avg_conf)}]{avg_conf:.0%}[/]  |  "
        f"DB ID: {result.id or 'not saved'}"
    )
    if not result.is_verified:
        console.print(
            "  [yellow]These results need human verification before going live.[/yellow]"
        )
    console.print()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scout",
        description="AI Scout — LLM-powered compliance research for JACE.",
    )
    parser.add_argument(
        "--state",
        required=True,
        help="State abbreviation (e.g., MT, CA)",
    )
    parser.add_argument(
        "--county",
        default="",
        help="County name (e.g., Gallatin, 'Los Angeles')",
    )
    parser.add_argument(
        "--city",
        default="",
        help="City name (e.g., Bozeman, 'San Francisco')",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save results to MongoDB",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    show_banner()

    state = args.state.strip().upper()
    county = args.county.strip() or None
    city = args.city.strip() or None

    # Display target
    target_parts = []
    if city:
        target_parts.append(f"City: {city}")
    if county:
        target_parts.append(f"County: {county}")
    target_parts.append(f"State: {state}")
    console.print(f"  [bold]Target:[/bold] {', '.join(target_parts)}")
    save_to_db = not args.no_save
    console.print(f"  [dim]Save to DB: {'Yes' if save_to_db else 'No (--no-save)'}[/dim]")
    console.print()

    # Initialize DB if saving
    if save_to_db:
        console.print("  [dim]Connecting to MongoDB...[/dim]")
        from db import init_db
        await init_db()

    # Run scout
    from scout import run_scout

    with console.status("[bold green]Research pass: GPT-4o analyzing jurisdiction...", spinner="dots"):
        result = await run_scout(
            state=state,
            county=county,
            city=city,
            save_to_db=save_to_db,
        )

    show_results(result)


if __name__ == "__main__":
    asyncio.run(main())
