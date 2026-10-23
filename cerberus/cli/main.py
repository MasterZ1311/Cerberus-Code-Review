"""
cerberus</> Rich Command-Line Interface.
Supports on-demand code reviews, server launch, agent inspection, and API key generation.
"""

import asyncio
from pathlib import Path
from typing import Optional
import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from cerberus import __version__
from cerberus.agents.orchestrator import orchestrator
from cerberus.config import settings
from cerberus.core.security import generate_api_key
from cerberus.models.schemas import CodeReviewRequest, ReviewConfig

app = typer.Typer(
    name="cerberus",
    help="cerberus</> - Autonomous Multi-Agent Code Review & Quality Assurance Platform",
    add_completion=False
)
console = Console()


@app.command()
def review(
    file_path: Optional[Path] = typer.Argument(None, help="Path to code file to review"),
    snippet: Optional[str] = typer.Option(None, "--snippet", "-s", help="Direct code snippet to review"),
    language: str = typer.Option("python", "--language", "-l", help="Language of code"),
    blocking: bool = typer.Option(False, "--blocking", "-b", help="Block with exit code 1 if critical/high flaws found"),
    agents: Optional[str] = typer.Option(None, "--agents", "-a", help="Comma-separated agents to run"),
):
    """Run autonomous multi-agent review on a file or code snippet."""
    code = ""
    filename = "snippet.py"

    if file_path:
        if not file_path.exists():
            console.print(f"[bold red]Error:[/bold run] File not found: {file_path}")
            raise typer.Exit(code=1)
        code = file_path.read_text(encoding="utf-8")
        filename = file_path.name
    elif snippet:
        code = snippet
    else:
        console.print("[bold red]Error:[/bold red] Provide either a file path or --snippet.")
        raise typer.Exit(code=1)

    agents_list = [a.strip() for a in agents.split(",")] if agents else None

    req = CodeReviewRequest(
        code=code,
        language=language,
        filename=filename,
        agents=agents_list,
        config=ReviewConfig(blocking_mode=blocking)
    )

    console.print(f"[bold cyan]cerberus</>[/bold cyan] [dim]v{__version__}[/dim] analyzing [bold]{filename}[/bold]...")

    # Execute orchestrator asynchronously
    response = asyncio.run(orchestrator.execute_review(req))

    # Display Results
    score_color = "green" if (response.overall_score or 0) >= 80 else ("yellow" if (response.overall_score or 0) >= 60 else "red")
    summary = response.results.get("severity_summary", {}) if response.results else {}

    console.print(Panel(
        f"[bold]Overall Quality Score:[/bold] [{score_color}]{response.overall_score} / 100[/{score_color}]\n"
        f"[bold]Latency:[/bold] {response.processing_time_ms}ms "
        f"{'⚡ [bold green](Cache Hit)[/bold green]' if response.cache_hit else ''}\n"
        f"[bold]Critical:[/bold] [red]{summary.get('critical', 0)}[/red] | "
        f"[bold]High:[/bold] [yellow]{summary.get('high', 0)}[/yellow] | "
        f"[bold]Medium:[/bold] {summary.get('medium', 0)} | "
        f"[bold]Low/Info:[/bold] {summary.get('low', 0) + summary.get('info', 0)}",
        title="[bold cyan]Review Summary[/bold cyan]",
        border_style="cyan"
    ))

    all_findings = response.critical_issues + response.warnings + response.suggestions

    if not all_findings:
        console.print("[bold green]✔ Zero vulnerabilities or quality issues detected![/bold green]")
    else:
        table = Table(title="Synthesized Agent Findings", show_header=True, header_style="bold magenta")
        table.add_column("Sev", width=10)
        table.add_column("Line", width=6)
        table.add_column("Category", width=14)
        table.add_column("Title & Suggested Remediation")

        for f in all_findings:
            sev_color = "red" if f.severity.value in ("critical", "high") else ("yellow" if f.severity.value == "medium" else "blue")
            details = f"[bold]{f.title}[/bold]\n[dim]{f.message}[/dim]"
            if f.suggestion:
                details += f"\n[green]Suggested Fix:[/green] {f.suggestion}"
            table.add_row(
                f"[{sev_color}]{f.severity.value.upper()}[/{sev_color}]",
                str(f.line or "-"),
                f.category,
                details
            )

        console.print(table)

    if blocking and response.should_block:
        console.print(f"[bold red]⛔ Blocking Commit/Push:[/bold red] {response.block_reason}")
        raise typer.Exit(code=1)


@app.command()
def create_api_key(
    name: str = typer.Option("default", "--name", "-n", help="Name or label for the API key")
):
    """Generate a cryptographically secure cerberus API key."""
    raw_key, key_hash, prefix = generate_api_key(name=name)

    async def _persist_key() -> None:
        from cerberus.core.database import AsyncSessionLocal, init_db
        from cerberus.models.database import ApiKeyRecord

        await init_db()
        async with AsyncSessionLocal() as session:
            record = ApiKeyRecord(
                key_hash=key_hash,
                name=name,
                prefix=prefix,
                scopes="review:read,review:write",
                is_active=True,
            )
            session.add(record)
            await session.commit()

    asyncio.run(_persist_key())

    console.print(Panel(
        f"[bold green]API Key created successfully![/bold green]\n\n"
        f"[bold]Key:[/bold] [yellow]{raw_key}[/yellow]\n"
        f"[bold]Name:[/bold] {name}\n"
        f"[dim]Store this key safely; use in Authorization: Bearer {raw_key}[/dim]",
        title="[bold cyan]cerberus</> Key Generator[/bold cyan]",
        border_style="green"
    ))


@app.command()
def list_agents():
    """List all available specialized agents and their capabilities."""
    agents_data = orchestrator.list_agents()
    table = Table(title="cerberus</> Agent Ecosystem", show_header=True, header_style="bold blue")
    table.add_column("Agent ID", width=14)
    table.add_column("Status", width=10)
    table.add_column("Purpose")
    table.add_column("Capabilities")

    for a in agents_data:
        status_col = "[green]ACTIVE[/green]" if a["status"] == "active" else "[dim]DISABLED[/dim]"
        caps = "\n• " + "\n• ".join(a["capabilities"][:4])
        if len(a["capabilities"]) > 4:
            caps += f"\n[dim]+ {len(a['capabilities']) - 4} more[/dim]"
        table.add_row(f"[bold]{a['id']}[/bold]", status_col, a["purpose"], caps)

    console.print(table)


@app.command()
def health():
    """Check system health, cache status, and active configuration."""
    provider_info = settings.LLM_PROVIDER
    if settings.LLM_PROVIDER == "watsonx":
        configured = bool(settings.WATSONX_API_KEY and settings.WATSONX_PROJECT_ID)
        status_tag = "[green]Ready (Credentials Active)[/green]" if configured else "[yellow]Awaiting Credentials in .env[/yellow]"
        provider_info = f"watsonx (IBM Granite) - {status_tag}"
    elif settings.LLM_PROVIDER == "openai":
        configured = bool(settings.OPENAI_API_KEY and len(settings.OPENAI_API_KEY) > 10)
        status_tag = "[green]Ready (API Key Active)[/green]" if configured else "[yellow]Awaiting OPENAI_API_KEY in .env[/yellow]"
        provider_info = f"openai ({settings.OPENAI_MODEL}) - {status_tag}"
    elif settings.LLM_PROVIDER == "ollama":
        provider_info = f"ollama ({settings.OLLAMA_MODEL}) @ {settings.OLLAMA_BASE_URL}"
    elif settings.LLM_PROVIDER == "heuristic":
        provider_info = "heuristic (Zero-Config Offline AST Engine)"

    console.print(Panel(
        f"[bold]Status:[/bold] [green]HEALTHY[/green]\n"
        f"[bold]Version:[/bold] {__version__}\n"
        f"[bold]LLM Provider:[/bold] {provider_info}\n"
        f"[bold]Active Agents:[/bold] {', '.join(settings.enabled_agents_list)}\n"
        f"[bold]Cache Enabled:[/bold] {settings.CACHE_ENABLED} (TTL: {settings.CACHE_TTL_SECONDS}s)\n"
        f"[bold]Web Dashboard:[/bold] http://{settings.HOST}:{settings.PORT}/",
        title="[bold cyan]cerberus</> System Status[/bold cyan]",
        border_style="cyan"
    ))


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Auto-reload on changes")
):
    """Launch the FastAPI server and visual Web Dashboard."""
    console.print(f"[bold cyan]Launching cerberus</> Server on http://{host}:{port}...[/bold cyan]")
    uvicorn.run("cerberus.api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
