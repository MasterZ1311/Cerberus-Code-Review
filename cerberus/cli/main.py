"""
cerberus</> Rich Command-Line Interface.
Supports on-demand code reviews, server launch, agent inspection, and API key generation.
"""

import asyncio
import os
from pathlib import Path
import sys
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
from cerberus.models.schemas import CodeReviewRequest, ReviewConfig, ZipReviewResponse

# Reconfigure stdout/stderr to utf-8 safely
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _safe_text(val: Optional[str]) -> str:
    """Normalize special unicode symbols that crash legacy Windows charmap encoders."""
    if not val:
        return ""
    text = str(val)
    replacements = {
        "\u2011": "-",
        "\u2013": "-",
        "\u2014": "--",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u00a0": " ",
        "•": "-",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _render_zip_review_cli(res: ZipReviewResponse, blocking: bool = False) -> None:
    """Renders comprehensive project archive review to CLI."""
    score_color = "green" if res.overall_project_score >= 80 else ("yellow" if res.overall_project_score >= 60 else "red")
    summary = res.severity_summary

    console.print(Panel(
        f"[bold]Project Name:[/bold] {res.project_name}\n"
        f"[bold]Overall Project Score:[/bold] [{score_color}]{res.overall_project_score} / 100[/{score_color}]\n"
        f"[bold]Files Reviewed:[/bold] {res.reviewed_files_count} / {res.total_files_discovered} files ({res.total_lines_of_code:,} LOC)\n"
        f"[bold]Skipped Files:[/bold] {res.skipped_files_count}\n"
        f"[bold]Languages:[/bold] {', '.join(f'{k} ({v})' for k, v in res.language_distribution.items()) if res.language_distribution else 'None'}\n"
        f"[bold]Critical:[/bold] [red]{summary.critical}[/red] | "
        f"[bold]High:[/bold] [yellow]{summary.high}[/yellow] | "
        f"[bold]Medium:[/bold] {summary.medium} | "
        f"[bold]Low/Info:[/bold] {summary.low + summary.info}\n"
        f"[bold]Latency:[/bold] {res.processing_time_ms}ms",
        title="[bold cyan]Project Archive Review Summary[/bold cyan]",
        border_style="cyan"
    ))

    # File breakdown table
    if res.file_reviews:
        table = Table(title=f"File-by-File Quality Breakdown ({len(res.file_reviews)} files)", show_header=True, header_style="bold magenta")
        table.add_column("File Path", style="cyan")
        table.add_column("Lang", width=10)
        table.add_column("LOC", width=6, justify="right")
        table.add_column("Score", width=8, justify="right")
        table.add_column("Crit", width=6, justify="right")
        table.add_column("High", width=6, justify="right")
        table.add_column("Med", width=6, justify="right")
        table.add_column("Status", width=10)

        for fr in res.file_reviews:
            f_color = "green" if fr.score >= 80 else ("yellow" if fr.score >= 60 else "red")
            crit_str = f"[red]{fr.critical_count}[/red]" if fr.critical_count > 0 else "0"
            high_str = f"[yellow]{fr.high_count}[/yellow]" if fr.high_count > 0 else "0"
            table.add_row(
                _safe_text(fr.file_path),
                fr.language,
                str(fr.lines_of_code),
                f"[{f_color}]{fr.score}[/{f_color}]",
                crit_str,
                high_str,
                str(fr.medium_count),
                "[green]PASS[/green]" if (fr.critical_count == 0 and fr.high_count == 0) else "[red]ISSUES[/red]"
            )

        console.print(table)

    # Top critical findings
    if res.top_critical_findings:
        crit_table = Table(title=f"Top Project Vulnerabilities & Critical Issues ({len(res.top_critical_findings)})", show_header=True, header_style="bold red")
        crit_table.add_column("Sev", width=10)
        crit_table.add_column("Category", width=14)
        crit_table.add_column("Issue & Context")

        for f in res.top_critical_findings[:15]:
            sev_col = "red" if f.severity.value == "critical" else "yellow"
            safe_title = _safe_text(f.title)
            safe_msg = _safe_text(f.message)
            crit_table.add_row(
                f"[{sev_col}]{f.severity.value.upper()}[/{sev_col}]",
                _safe_text(f.category),
                f"[bold]{safe_title}[/bold]\n[dim]{safe_msg}[/dim]"
            )
        console.print(crit_table)

    # Consensus
    if res.collaborative_consensus:
        cc = res.collaborative_consensus
        pr_action = cc.get("pr_action", "MERGE_READY").replace(" ", "_").upper()
        action_color = "green" if pr_action == "MERGE_READY" else ("yellow" if pr_action == "NEEDS_REVISION" else "red")
        plans = [_safe_text(p) for p in cc.get('priority_action_plan', [])] if cc.get('priority_action_plan') else []
        console.print(Panel(
            f"[bold]Project Consensus Verdict:[/bold] [{action_color}]{pr_action.replace('_', ' ')}[/{action_color}]\n"
            f"[bold]Summary:[/bold] {_safe_text(cc.get('summary'))}\n"
            + (f"[dim]Plan: {', '.join(plans)}[/dim]" if plans else ""),
            title="[bold cyan][PROJECT CONSENSUS] Multi-Agent Alignment[/bold cyan]",
            border_style=action_color
        ))

    if blocking and (summary.critical > 0 or summary.high > 0):
        console.print(f"[bold red][BLOCKED] Project failed blocking threshold with {summary.critical} critical and {summary.high} high issues.[/bold red]")
        raise typer.Exit(code=1)


app = typer.Typer(
    name="cerberus",
    help="cerberus</> - Autonomous Multi-Agent Code Review & Quality Assurance Platform",
    add_completion=False
)
console = Console()


@app.command()
def review(
    file_path: Optional[Path] = typer.Argument(None, help="Path to code file or ZIP archive to review"),
    snippet: Optional[str] = typer.Option(None, "--snippet", "-s", help="Direct code snippet to review"),
    zip_file: Optional[Path] = typer.Option(None, "--zip", "-z", help="Direct path to ZIP project archive to review"),
    language: str = typer.Option("python", "--language", "-l", help="Language of code"),
    blocking: bool = typer.Option(False, "--blocking", "-b", help="Block with exit code 1 if critical/high flaws found"),
    agents: Optional[str] = typer.Option(None, "--agents", "-a", help="Comma-separated agents to run"),
):
    """Run autonomous multi-agent review on a file, code snippet, or ZIP archive."""
    agents_list = [a.strip() for a in agents.split(",") if a.strip()] if agents else None

    # Check for ZIP project review
    target_zip = zip_file or (file_path if file_path and file_path.suffix.lower() == ".zip" else None)
    if target_zip:
        if not target_zip.exists():
            console.print(f"[bold red]Error:[/bold red] ZIP file not found: {target_zip}")
            raise typer.Exit(code=1)

        console.print(f"[bold cyan]cerberus</>[/bold cyan] [dim]v{__version__}[/dim] extracting and reviewing project archive: [bold]{target_zip.name}[/bold]...")

        try:
            zip_response = asyncio.run(orchestrator.execute_zip_review(
                zip_source=target_zip,
                project_name=target_zip.stem,
                agents=agents_list,
                config=ReviewConfig(blocking_mode=blocking)
            ))
        except Exception as e:
            console.print(f"[bold red]Extraction/Review Error:[/bold red] {e}")
            raise typer.Exit(code=1)

        _render_zip_review_cli(zip_response, blocking)
        return

    code = ""
    filename = "snippet.py"

    if file_path:
        if not file_path.exists():
            console.print(f"[bold red]Error:[/bold red] File not found: {file_path}")
            raise typer.Exit(code=1)
        code = file_path.read_text(encoding="utf-8")
        filename = file_path.name
    elif snippet:
        code = snippet
    else:
        console.print("[bold red]Error:[/bold red] Provide a code file, .zip archive, or --snippet.")
        raise typer.Exit(code=1)

    agents_list = [a.strip() for a in agents.split(",") if a.strip()] if agents else None

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
        f"{'[bold green][Cache Hit][/bold green]' if response.cache_hit else ''}\n"
        f"[bold]Critical:[/bold] [red]{summary.get('critical', 0)}[/red] | "
        f"[bold]High:[/bold] [yellow]{summary.get('high', 0)}[/yellow] | "
        f"[bold]Medium:[/bold] {summary.get('medium', 0)} | "
        f"[bold]Low/Info:[/bold] {summary.get('low', 0) + summary.get('info', 0)}",
        title="[bold cyan]Review Summary[/bold cyan]",
        border_style="cyan"
    ))

    all_findings = response.critical_issues + response.warnings + response.suggestions

    if not all_findings:
        console.print("[bold green][OK] Zero vulnerabilities or quality issues detected![/bold green]")
    else:
        table = Table(title="Synthesized Agent Findings", show_header=True, header_style="bold magenta")
        table.add_column("Sev", width=10)
        table.add_column("Line", width=6)
        table.add_column("Category", width=14)
        table.add_column("Title & Suggested Remediation")

        for f in all_findings:
            sev_color = "red" if f.severity.value in ("critical", "high") else ("yellow" if f.severity.value == "medium" else "blue")
            safe_title = _safe_text(f.title)
            safe_msg = _safe_text(f.message)
            safe_fix = _safe_text(f.suggestion)
            details = f"[bold]{safe_title}[/bold]\n[dim]{safe_msg}[/dim]"
            if safe_fix:
                details += f"\n[green]Suggested Fix:[/green] {safe_fix}"
            table.add_row(
                f"[{sev_color}]{f.severity.value.upper()}[/{sev_color}]",
                str(f.line or "-"),
                _safe_text(f.category),
                details
            )

        console.print(table)

    # Multi-Agent Collaborative Consensus
    if response.collaborative_consensus:
        cc = response.collaborative_consensus
        pr_action = cc.get("pr_action", "MERGE_READY").replace(" ", "_").upper()
        action_color = "green" if pr_action == "MERGE_READY" else ("yellow" if pr_action == "NEEDS_REVISION" else "red")
        safe_summary = _safe_text(cc.get('summary'))
        safe_plan = [_safe_text(p) for p in cc.get('priority_action_plan', [])]
        console.print(Panel(
            f"[bold]Consensus Verdict:[/bold] [{action_color}]{pr_action.replace('_', ' ')}[/{action_color}]\n"
            f"[bold]Summary:[/bold] {safe_summary}\n"
            + (f"[dim]Plan: {', '.join(safe_plan)}[/dim]" if safe_plan else ""),
            title="[bold cyan][COLLABORATIVE CONSENSUS] Multi-Agent Alignment[/bold cyan]",
            border_style=action_color
        ))

    # Multi-Agent Automated Unified Patch
    if response.unified_patch:
        console.print(Panel(
            f"[green]{_safe_text(response.unified_patch)}[/green]",
            title="[bold green][AUTOMATED PATCH] Multi-Agent Consolidated Fix (Git Unified Diff)[/bold green]",
            border_style="green"
        ))

    if blocking and response.should_block:
        console.print(f"[bold red][BLOCKED] Blocking Commit/Push:[/bold red] {response.block_reason}")
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
def list_api_keys():
    """List all registered API keys and their active status."""
    async def _query():
        from cerberus.core.database import AsyncSessionLocal, init_db
        from cerberus.models.database import ApiKeyRecord
        from sqlalchemy import select

        await init_db()
        async with AsyncSessionLocal() as session:
            stmt = select(ApiKeyRecord)
            res = await session.execute(stmt)
            return res.scalars().all()

    keys = asyncio.run(_query())
    table = Table(title="cerberus</> Registered API Keys", show_header=True, header_style="bold green")
    table.add_column("Key Name", style="cyan")
    table.add_column("Prefix", width=8)
    table.add_column("Status", width=10)
    table.add_column("Created", width=22)

    for k in keys:
        st = "[green]ACTIVE[/green]" if k.is_active else "[red]REVOKED[/red]"
        table.add_row(k.name, k.prefix, st, str(k.created_at)[:19])

    console.print(table)


@app.command()
def revoke_api_key(
    name: str = typer.Argument(..., help="Name of the API key to revoke")
):
    """Revoke an active API key by its identifier name."""
    async def _revoke():
        from cerberus.core.database import AsyncSessionLocal, init_db
        from cerberus.models.database import ApiKeyRecord
        from sqlalchemy import select

        await init_db()
        async with AsyncSessionLocal() as session:
            stmt = select(ApiKeyRecord).where(ApiKeyRecord.name == name)
            res = await session.execute(stmt)
            record = res.scalars().first()
            if record:
                record.is_active = False
                await session.commit()
                return True
            return False

    revoked = asyncio.run(_revoke())
    if revoked:
        console.print(f"[bold green]API key '{name}' has been successfully revoked.[/bold green]")
    else:
        console.print(f"[bold red]API key with name '{name}' not found.[/bold red]")


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
        caps = "\n- " + "\n- ".join(a["capabilities"][:4])
        if len(a["capabilities"]) > 4:
            caps += f"\n[dim]+ {len(a['capabilities']) - 4} more[/dim]"
        table.add_row(f"[bold]{a['id']}[/bold]", status_col, a["purpose"], caps)

    console.print(table)


@app.command()
def health():
    """Check system health, cache status, and active configuration."""
    from cerberus.providers import resolve_auto_provider
    active_prov = resolve_auto_provider() if settings.LLM_PROVIDER in ("auto", "detect", "") else settings.LLM_PROVIDER

    configured_keys = []
    if settings.GROQ_API_KEY:
        configured_keys.append("Groq")
    if settings.OPENAI_API_KEY:
        configured_keys.append("OpenAI")
    if settings.ANTHROPIC_API_KEY:
        configured_keys.append("Anthropic")
    if settings.GEMINI_API_KEY:
        configured_keys.append("Gemini")
    if settings.DEEPSEEK_API_KEY:
        configured_keys.append("DeepSeek")
    if getattr(settings, "WATSONX_API_KEY", None):
        configured_keys.append("Watsonx (Legacy)")

    keys_status = f"[green]{', '.join(configured_keys)}[/green]" if configured_keys else "[dim]None (Running Heuristic Engine)[/dim]"
    prov_display = f"{active_prov.upper()} (Active)" if active_prov != "heuristic" else "Heuristic (Offline AST Engine)"

    console.print(Panel(
        f"[bold]Status:[/bold] [green]HEALTHY[/green]\n"
        f"[bold]Version:[/bold] {__version__}\n"
        f"[bold]Active LLM Provider:[/bold] {prov_display}\n"
        f"[bold]Detected API Keys:[/bold] {keys_status}\n"
        f"[bold]Multi-Agent Collaboration:[/bold] [green]Active[/green] (Consensus + Code Fixer)\n"
        f"[bold]Active Agents:[/bold] {', '.join(settings.enabled_agents_list)}\n"
        f"[bold]Cache Enabled:[/bold] {settings.CACHE_ENABLED} (TTL: {settings.CACHE_TTL_SECONDS}s)\n"
        f"[bold]Web Dashboard:[/bold] http://{settings.HOST}:{settings.PORT}/",
        title="[bold cyan]cerberus</> System Status[/bold cyan]",
        border_style="cyan"
    ))


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="Bind host"),
    port: int = typer.Option(settings.PORT, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Auto-reload on changes")
):
    """Launch the FastAPI server and visual Web Dashboard."""
    console.print(f"[bold cyan]Launching cerberus</> Server on http://{host}:{port}...[/bold cyan]")
    uvicorn.run("cerberus.api.app:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    app()
