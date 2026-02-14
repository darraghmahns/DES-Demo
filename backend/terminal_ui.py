"""Rich-based terminal UI for the DocExtract CLI demo."""

import json
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text

console = Console()

BANNER_LINES = [
    r"    ____             ______     __                  __  ",
    r"   / __ \____  _____/ ____/  __/ /__________ ______/ /_ ",
    r"  / / / / __ \/ ___/ __/ | |/_/ __/ ___/ __ `/ ___/ __/",
    r" / /_/ / /_/ / /__/ /____>  </ /_/ /  / /_/ / /__/ /_  ",
    r"/_____/\____/\___/_____/_/|_|\__/_/   \__,_/\___/\__/  ",
]


def show_banner():
    """Display the main application banner."""
    console.print()
    art_width = max(len(line) for line in BANNER_LINES)
    # Panel uses 2 border chars + padding (1,2) means 2 chars each side = 6 total
    inner_width = console.width - 2 - 4  # border + padding
    pad = max(0, (inner_width - art_width) // 2)
    centered = [" " * pad + line.ljust(art_width) for line in BANNER_LINES]
    art = "\n".join(centered)
    console.print(
        Panel(
            Text(art, style="bold cyan", no_wrap=True),
            title="[bold white]Document Intelligence Engine[/]",
            subtitle="[dim]Neural OCR  +  Pydantic Validation[/]",
            border_style="cyan",
            padding=(1, 2),
        )
    )
    console.print()


def show_mode_info(mode: str, input_path: str):
    """Display the current mode and input file."""
    mode_label = "Real Estate (Dotloop)" if mode == "real_estate" else "Government (FOIA)"
    mode_color = "blue" if mode == "real_estate" else "magenta"
    console.print(f"  [{mode_color}]Mode:[/{mode_color}]  {mode_label}")
    console.print(f"  [dim]Input:[/dim] {input_path}")
    console.print()


def show_step(step_num: int, total_steps: int, title: str, description: str):
    """Display a step header panel."""
    console.print()
    console.print(
        Panel(
            f"[dim]{description}[/]",
            title=f"[bold yellow]Step {step_num}/{total_steps}[/] [bold white]{title}[/]",
            border_style="yellow",
            padding=(0, 2),
        )
    )


def show_file_info(name: str, size: str, pages: int):
    """Display file metadata."""
    console.print(f"  [green]\u2713[/] File:  [bold]{name}[/]")
    console.print(f"  [green]\u2713[/] Size:  {size}")
    console.print(f"  [green]\u2713[/] Pages: {pages}")


def show_extraction_table(data: dict, mode: str):
    """Display extracted data as a color-coded table."""
    mode_label = "Real Estate" if mode == "real_estate" else "FOIA"
    table = Table(
        title=f"Extracted Fields ({mode_label})",
        show_lines=True,
        title_style="bold white",
        border_style="dim",
    )
    table.add_column("Field", style="cyan", width=30, no_wrap=True)
    table.add_column("Value", style="white", width=55)
    table.add_column("", justify="center", width=4)

    flat = _flatten_dict(data)
    for key, value in flat.items():
        if value is not None and value != "" and value != []:
            display_val = str(value)
            if len(display_val) > 55:
                display_val = display_val[:52] + "..."
            status = "[green]\u2713[/]"
        else:
            display_val = "[dim]--[/]"
            status = "[yellow]\u25cb[/]"
        table.add_row(key, display_val, status)

    console.print()
    console.print(table)


def show_validation_result(success: bool, errors: list[str] | None = None):
    """Display Pydantic validation result."""
    if success:
        console.print()
        console.print(
            Panel(
                "[green]All fields passed Pydantic schema validation[/]",
                title="[bold green]\u2713 Validation Passed[/]",
                border_style="green",
                padding=(0, 2),
            )
        )
    else:
        error_text = "\n".join(f"  [red]\u2717[/] {e}" for e in (errors or []))
        console.print()
        console.print(
            Panel(
                error_text,
                title="[bold red]\u2717 Validation Errors[/]",
                border_style="red",
                padding=(0, 2),
            )
        )


def show_citation_table(citations: list[dict]):
    """Display verification citations in a table."""
    table = Table(
        title="Verification Citations",
        show_lines=True,
        title_style="bold white",
        border_style="dim",
    )
    table.add_column("Field", style="cyan", width=22, no_wrap=True)
    table.add_column("Value", width=22)
    table.add_column("Page", justify="center", width=5)
    table.add_column("Location", width=18)
    table.add_column("Context", width=28, style="dim")
    table.add_column("Conf.", justify="center", width=6)

    for c in citations:
        conf = c.get("confidence", 0)
        if conf >= 0.9:
            conf_str = f"[green]{conf:.0%}[/]"
        elif conf >= 0.7:
            conf_str = f"[yellow]{conf:.0%}[/]"
        else:
            conf_str = f"[red]{conf:.0%}[/]"

        value_str = str(c.get("extracted_value", ""))
        if len(value_str) > 22:
            value_str = value_str[:19] + "..."

        context_str = str(c.get("surrounding_text", ""))
        if len(context_str) > 28:
            context_str = context_str[:25] + "..."

        table.add_row(
            c.get("field_name", ""),
            value_str,
            str(c.get("page_number", "")),
            c.get("line_or_region", ""),
            context_str,
            conf_str,
        )

    console.print()
    console.print(table)


def show_confidence_bar(confidence: float):
    """Show overall confidence as a colored progress bar."""
    if confidence >= 0.85:
        color = "green"
    elif confidence >= 0.65:
        color = "yellow"
    else:
        color = "red"

    bar_width = 30
    filled = int(confidence * bar_width)
    empty = bar_width - filled
    bar = f"[{color}]{'█' * filled}[/{color}][dim]{'░' * empty}[/]"

    console.print()
    console.print(f"  Overall Confidence: {bar} [{color}]{confidence:.1%}[/{color}]")
    console.print()


def show_pii_findings(findings: list[dict]):
    """Render PII findings with risk visualization."""
    if not findings:
        console.print()
        console.print("  [green]No PII detected.[/]")
        return

    table = Table(
        title="PII Detection Results",
        show_lines=True,
        title_style="bold white",
        border_style="dim",
    )
    table.add_column("Type", style="bold", width=8)
    table.add_column("Redacted Value", width=22)
    table.add_column("Location", width=18)
    table.add_column("Risk", justify="center", width=8)
    table.add_column("Recommendation", width=45)

    severity_colors = {"HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}

    for f in findings:
        sev = f.get("severity", "LOW")
        color = severity_colors.get(sev, "white")
        table.add_row(
            f.get("pii_type", ""),
            f.get("value_redacted", ""),
            f.get("location", ""),
            f"[{color}]{sev}[/{color}]",
            f.get("recommendation", ""),
        )

    console.print()
    console.print(table)


def show_pii_risk_score(score: int, level: str):
    """Display the aggregate PII risk score."""
    if level == "HIGH":
        color = "red"
    elif level == "MEDIUM":
        color = "yellow"
    else:
        color = "green"

    console.print()
    console.print(
        Panel(
            f"[{color} bold]PII Risk Score: {score}/100  ({level})[/{color} bold]",
            border_style=color,
            padding=(0, 2),
        )
    )


def show_json_output(data: dict, output_path: str):
    """Pretty-print final JSON with syntax highlighting."""
    json_str = json.dumps(data, indent=2, default=str)
    # Truncate for display if very long
    lines = json_str.split("\n")
    if len(lines) > 60:
        display_str = "\n".join(lines[:55]) + "\n  ...\n" + "\n".join(lines[-3:])
    else:
        display_str = json_str

    syntax = Syntax(display_str, "json", theme="monokai", line_numbers=True)
    console.print()
    console.print(
        Panel(
            syntax,
            title=f"[bold green]Output: {output_path}[/]",
            border_style="green",
            padding=(0, 1),
        )
    )


def show_complete(mode: str, pages: int, fields: int, output_path: str):
    """Display the final completion panel."""
    mode_label = "Real Estate (Dotloop)" if mode == "real_estate" else "Government (FOIA)"
    console.print()
    console.print(
        Panel(
            f"[green bold]Extraction complete.[/]\n\n"
            f"  Mode:   {mode_label}\n"
            f"  Pages:  {pages}\n"
            f"  Fields: {fields}\n"
            f"  Output: [underline]{output_path}[/]",
            title="[bold green]\u2713 Done[/]",
            border_style="green",
            padding=(1, 2),
        )
    )
    console.print()


def show_error(title: str, message: str):
    """Display an error panel."""
    console.print()
    console.print(
        Panel(
            f"[red]{message}[/]",
            title=f"[bold red]{title}[/]",
            border_style="red",
            padding=(0, 2),
        )
    )
    console.print()


def _flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Flatten a nested dict for table display."""
    items: list[tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            if v and isinstance(v[0], dict):
                for i, item in enumerate(v):
                    items.extend(_flatten_dict(item, f"{new_key}[{i}]", sep=sep).items())
            else:
                items.append((new_key, v))
        else:
            items.append((new_key, v))
    return dict(items)
