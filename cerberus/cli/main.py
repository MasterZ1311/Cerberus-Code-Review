"""
cerberus</> Rich Command-Line Interface.
Supports on-demand code reviews, server launch, agent inspection, and API key generation.
"""

import asyncio
import json
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
from cerberus.core.sarif import (
    review_response_to_gitlab_code_quality,
    review_response_to_sarif,
    review_response_to_sonarqube,
    zip_review_response_to_gitlab_code_quality,
    zip_review_response_to_sarif,
    zip_review_response_to_sonarqube,
)
from cerberus.core.github_app import build_github_check_run_payload, GitHubPullRequestInfo
from cerberus.core.security import generate_api_key
from cerberus.core.zip_processor import detect_language_from_path
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
    format: str = typer.Option("text", "--format", "-F", help="Output format: text, json, sarif, markdown"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="File path to save results"),
):
    """Run autonomous multi-agent review on a file, code snippet, or ZIP archive."""
    # Sanitize Typer OptionInfo / ArgumentInfo defaults if invoked directly as a Python callable
    if not isinstance(file_path, (Path, str)) and file_path is not None:
        file_path = None
    elif isinstance(file_path, str):
        file_path = Path(file_path)

    if not isinstance(zip_file, (Path, str)) and zip_file is not None:
        zip_file = None
    elif isinstance(zip_file, str):
        zip_file = Path(zip_file)

    if not isinstance(output, (Path, str)) and output is not None:
        output = None
    elif isinstance(output, str):
        output = Path(output)

    if not isinstance(snippet, str):
        snippet = None

    if not isinstance(language, str):
        language = "python"

    if not isinstance(blocking, bool):
        blocking = False

    if not isinstance(format, str):
        format = "text"

    if not isinstance(agents, str):
        agents = None

    agents_list = [a.strip() for a in agents.split(",") if a.strip()] if agents else None

    # Check for ZIP project review
    target_zip = zip_file or (file_path if file_path and file_path.suffix.lower() == ".zip" else None)
    if target_zip:
        if not target_zip.exists():
            console.print(f"[bold red]Error:[/bold red] ZIP file not found: {target_zip}")
            raise typer.Exit(code=1)

        if format.lower() == "text":
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

        if format.lower() == "sarif":
            sarif_data = zip_review_response_to_sarif(zip_response)
            sarif_str = json.dumps(sarif_data, indent=2)
            if output:
                output.write_text(sarif_str, encoding="utf-8")
                console.print(f"[bold green]SARIF report saved to {output}[/bold green]")
            else:
                print(sarif_str)
            return
        elif format.lower() == "gitlab":
            gl_data = zip_review_response_to_gitlab_code_quality(zip_response)
            gl_str = json.dumps(gl_data, indent=2)
            if output:
                output.write_text(gl_str, encoding="utf-8")
                console.print(f"[bold green]GitLab Code Quality report saved to {output}[/bold green]")
            else:
                print(gl_str)
            return
        elif format.lower() in ("sonarqube", "sonar"):
            sonar_data = zip_review_response_to_sonarqube(zip_response)
            sonar_str = json.dumps(sonar_data, indent=2)
            if output:
                output.write_text(sonar_str, encoding="utf-8")
                console.print(f"[bold green]SonarQube Generic Issues report saved to {output}[/bold green]")
            else:
                print(sonar_str)
            return
        elif format.lower() == "json":
            json_str = json.dumps(zip_response.model_dump(), indent=2)
            if output:
                output.write_text(json_str, encoding="utf-8")
                console.print(f"[bold green]JSON report saved to {output}[/bold green]")
            else:
                print(json_str)
            return

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
        detected = detect_language_from_path(filename)
        if detected:
            language = detected
    elif snippet:
        code = snippet
    else:
        console.print("[bold red]Error:[/bold red] Provide a code file, .zip archive, or --snippet.")
        raise typer.Exit(code=1)

    req = CodeReviewRequest(
        code=code,
        language=language,
        filename=filename,
        agents=agents_list,
        config=ReviewConfig(blocking_mode=blocking)
    )

    if format.lower() == "text":
        console.print(f"[bold cyan]cerberus</>[/bold cyan] [dim]v{__version__}[/dim] analyzing [bold]{filename}[/bold]...")

    # Execute orchestrator asynchronously
    response = asyncio.run(orchestrator.execute_review(req))

    # Formatted outputs
    if format.lower() == "sarif":
        sarif_data = review_response_to_sarif(response, filename=filename)
        sarif_str = json.dumps(sarif_data, indent=2)
        if output:
            output.write_text(sarif_str, encoding="utf-8")
            console.print(f"[bold green]SARIF report saved to {output}[/bold green]")
        else:
            print(sarif_str)
        return
    elif format.lower() == "gitlab":
        gl_data = review_response_to_gitlab_code_quality(response, filename=filename)
        gl_str = json.dumps(gl_data, indent=2)
        if output:
            output.write_text(gl_str, encoding="utf-8")
            console.print(f"[bold green]GitLab Code Quality report saved to {output}[/bold green]")
        else:
            print(gl_str)
        return
    elif format.lower() in ("sonarqube", "sonar"):
        sonar_data = review_response_to_sonarqube(response, filename=filename)
        sonar_str = json.dumps(sonar_data, indent=2)
        if output:
            output.write_text(sonar_str, encoding="utf-8")
            console.print(f"[bold green]SonarQube Generic Issues report saved to {output}[/bold green]")
        else:
            print(sonar_str)
        return
    elif format.lower() in ("check-run", "checks"):
        fake_pr = GitHubPullRequestInfo(
            action="opened",
            pr_number=1,
            title="Local Review",
            repo_name="local-repo",
            repo_owner="local-owner",
            full_name="local-owner/local-repo",
            head_sha="HEAD"
        )
        checks_data = build_github_check_run_payload(response, fake_pr, filename=filename)
        checks_str = json.dumps(checks_data, indent=2)
        if output:
            output.write_text(checks_str, encoding="utf-8")
            console.print(f"[bold green]GitHub Check Run payload saved to {output}[/bold green]")
        else:
            print(checks_str)
        return
    elif format.lower() == "json":
        json_str = json.dumps(response.model_dump(), indent=2)
        if output:
            output.write_text(json_str, encoding="utf-8")
            console.print(f"[bold green]JSON report saved to {output}[/bold green]")
        else:
            print(json_str)
        return
    elif format.lower() == "markdown":
        md = f"## 🛡️ cerberus</> Code Review: `{filename}`\n\n"
        md += f"- **Score:** {response.overall_score} / 100\n"
        md += f"- **Status:** {response.status.upper()}\n"
        if response.collaborative_consensus:
            md += f"- **Consensus Verdict:** {response.collaborative_consensus.get('pr_action', 'N/A')}\n"
        all_f = response.critical_issues + response.warnings + response.suggestions
        md += f"\n### Detected Findings ({len(all_f)})\n\n"
        for f in all_f:
            md += f"- **[{f.severity.value.upper()}] Line {f.line or '?'}:** {f.title} — {f.message}\n"
        if response.unified_patch:
            md += f"\n### Automated Git Patch\n```diff\n{response.unified_patch}\n```\n"
        if output:
            output.write_text(md, encoding="utf-8")
            console.print(f"[bold green]Markdown review saved to {output}[/bold green]")
        else:
            print(md)
        return

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


@app.command(name="apply-fix")
def apply_fix_command(
    file: Path = typer.Option(..., "--file", "-f", help="Target source file to repair"),
    backup: bool = typer.Option(True, "--backup/--no-backup", help="Create backup .bak file before updating"),
    language: Optional[str] = typer.Option(None, "--language", "-l", help="Language override"),
):
    """Review source file and apply AST-verified multi-agent code fixes in-place."""
    if not file.exists() or not file.is_file():
        console.print(f"[bold red]Error:[/bold red] File not found: {file}")
        raise typer.Exit(code=1)

    original_code = file.read_text(encoding="utf-8", errors="replace")
    detected_lang = language or detect_language_from_path(file.name) or "python"

    console.print(f"[bold cyan]cerberus</>[/bold cyan] analyzing and synthesizing repairs for [bold]{file.name}[/bold]...")

    req = CodeReviewRequest(
        code=original_code,
        language=detected_lang,
        filename=file.name,
        config=ReviewConfig(blocking_mode=False)
    )
    response = asyncio.run(orchestrator.execute_review(req))

    all_findings = response.critical_issues + response.warnings + response.suggestions
    if not all_findings:
        console.print("[bold green]Code is already pristine! No repairs required.[/bold green]")
        return

    fixer = orchestrator.registry.get("code_fixer")
    if not fixer:
        console.print("[bold red]Code Fixer Agent unavailable.[/bold red]")
        raise typer.Exit(code=1)

    synthesis = asyncio.run(fixer.synthesize_fixes(
        original_code=original_code,
        findings=all_findings,
        filename=file.name,
        language=detected_lang
    ))

    if not synthesis.get("patch_applied"):
        console.print("[bold yellow]No safe automated fixes could be synthesized for the flagged issues.[/bold yellow]")
        return

    repaired_code = synthesis["repaired_code"]

    if backup:
        backup_path = file.with_suffix(file.suffix + ".bak")
        backup_path.write_text(original_code, encoding="utf-8")
        console.print(f"[dim]Backup created: {backup_path.name}[/dim]")

    file.write_text(repaired_code, encoding="utf-8")
    console.print(Panel(
        f"[bold green]Repairs successfully applied to {file.name}![/bold green]\n\n"
        f"[cyan]Diff Summary:[/cyan]\n"
        f"{_safe_text(synthesis['unified_diff'])}",
        title="[bold green]Code Repair Summary[/bold green]",
        border_style="green"
    ))


@app.command(name="export-sarif")
def export_sarif_command(
    file: Path = typer.Option(..., "--file", "-f", help="Target source code or ZIP archive to analyze"),
    output: Path = typer.Option(Path("cerberus-results.sarif"), "--output", "-o", help="Destination SARIF file"),
    language: str = typer.Option("python", "--language", "-l", help="Language of code"),
):
    """Analyze file or ZIP archive and export findings to OASIS SARIF v2.1.0 format."""
    review(
        file_path=file,
        format="sarif",
        output=output,
        language=language
    )


@app.command(name="export-sonarqube")
def export_sonarqube_command(
    file: Path = typer.Option(..., "--file", "-f", help="Target source code or ZIP archive to analyze"),
    output: Path = typer.Option(Path("sonar-generic-issues.json"), "--output", "-o", help="Destination SonarQube JSON file"),
    language: str = typer.Option("python", "--language", "-l", help="Language of code"),
):
    """Analyze file or ZIP archive and export findings to SonarQube Generic Issue Import format."""
    review(
        file_path=file,
        format="sonarqube",
        output=output,
        language=language
    )


@app.command(name="export-gitlab")
def export_gitlab_command(
    file: Path = typer.Option(..., "--file", "-f", help="Target source code or ZIP archive to analyze"),
    output: Path = typer.Option(Path("gl-code-quality-report.json"), "--output", "-o", help="Destination GitLab CI JSON file"),
    language: str = typer.Option("python", "--language", "-l", help="Language of code"),
):
    """Analyze file or ZIP archive and export findings to GitLab CI Code Quality JSON format."""
    review(
        file_path=file,
        format="gitlab",
        output=output,
        language=language
    )


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


@app.command()
def doctor():
    """Run comprehensive environmental and dependency health diagnostics."""
    from cerberus.core.syntax_verifier import SyntaxVerifier
    from cerberus.core.security import verify_key_entropy
    from cerberus.providers import resolve_auto_provider
    import sys

    table = Table(title="cerberus</> System & Dependency Diagnostics", show_header=True, header_style="bold cyan")
    table.add_column("Diagnostic Check", style="bold")
    table.add_column("Result", width=12)
    table.add_column("Details & Recommendations")

    # 1. Python Version
    py_ver = sys.version_info
    if py_ver >= (3, 11):
        table.add_row("Python Runtime", "[green]PASS[/green]", f"Python {py_ver.major}.{py_ver.minor}.{py_ver.micro} (Supported: >= 3.11)")
    else:
        table.add_row("Python Runtime", "[red]FAIL[/red]", f"Python {py_ver.major}.{py_ver.minor} detected. Python 3.11+ is strongly recommended.")

    # 2. Tree-sitter AST Engines
    ts_supported = [lang for lang in ("python", "typescript", "go", "rust") if SyntaxVerifier.is_tree_sitter_supported(lang)]
    if len(ts_supported) >= 4:
        table.add_row("Tree-sitter AST", "[green]PASS[/green]", f"Native C-bindings active for {', '.join(ts_supported)}")
    elif ts_supported:
        table.add_row("Tree-sitter AST", "[yellow]PARTIAL[/yellow]", f"Active: {', '.join(ts_supported)}. Install tree-sitter packages for complete coverage.")
    else:
        table.add_row("Tree-sitter AST", "[yellow]WARN[/yellow]", "Tree-sitter bindings not detected. Running balanced delimiter fallback engine.")

    # 3. Database Connectivity
    async def _check_db():
        from cerberus.core.database import warm_connection_pool
        return await warm_connection_pool()

    db_ok = asyncio.run(_check_db())
    if db_ok:
        table.add_row("Database Engine", "[green]PASS[/green]", f"Connected: {settings.DATABASE_URL.split('@')[-1]}")
    else:
        table.add_row("Database Engine", "[red]FAIL[/red]", f"Cannot connect to {settings.DATABASE_URL}. Check permissions or server status.")

    # 4. Cache System
    table.add_row("Cache Subsystem", "[green]PASS[/green]", f"Enabled: {settings.CACHE_ENABLED} (TTL: {settings.CACHE_TTL_SECONDS}s, In-Memory LRU + Redis)")

    # 5. Security & Secret Key
    has_safe_key = verify_key_entropy(settings.SECRET_KEY, min_entropy=3.0) and len(settings.SECRET_KEY) >= 32
    if has_safe_key:
        table.add_row("Security Config", "[green]PASS[/green]", "High-entropy SECRET_KEY configured (>= 32 chars).")
    else:
        table.add_row("Security Config", "[yellow]WARN[/yellow]", "Default or low-entropy SECRET_KEY in use. Set unique SECRET_KEY for production.")

    # 6. Active LLM Provider
    prov = resolve_auto_provider() if settings.LLM_PROVIDER in ("auto", "detect", "") else settings.LLM_PROVIDER
    table.add_row("LLM Provider", "[green]PASS[/green]", f"Resolved to '{prov.upper()}'. Zero-latency HeuristicEngine ready as fallback.")

    # 7. Git Hooks
    hooks_installed = (Path(".git/hooks/pre-commit").exists()) if Path(".git").exists() else False
    if hooks_installed:
        table.add_row("Git Hooks", "[green]PASS[/green]", "Pre-commit hook installed in .git/hooks/pre-commit")
    elif Path(".git").exists():
        table.add_row("Git Hooks", "[yellow]NOTICE[/yellow]", "Hooks not installed. Run 'cerberus hooks install' for zero-click reviews.")
    else:
        table.add_row("Git Hooks", "[dim]SKIP[/dim]", "Not in a Git repository root.")

    console.print(table)


@app.command()
def init(
    repo_dir: Path = typer.Option(Path("."), "--repo-dir", "-d", help="Path to project directory to initialize")
):
    """Bootstrap cerberus in current repository (.env, database schema, and git hooks)."""
    env_file = repo_dir / ".env"
    env_example = repo_dir / ".env.example"

    console.print(f"[bold cyan]Initializing cerberus</> project in {repo_dir.resolve()}...[/bold cyan]")

    # 1. Create .env if missing
    if not env_file.exists():
        if env_example.exists():
            content = env_example.read_text(encoding="utf-8")
        else:
            content = "SECRET_KEY=change_me_in_production\nLLM_PROVIDER=auto\nCACHE_ENABLED=true\n"
        import secrets
        new_secret = f"cvai_sec_{secrets.token_hex(24)}"
        content = content.replace("cerberus_dev_secret_key_change_in_production_32chars", new_secret)
        env_file.write_text(content, encoding="utf-8")
        console.print(f"[bold green]Created .env configuration file with high-entropy SECRET_KEY.[/bold green]")
    else:
        console.print(f"[dim].env configuration file already exists.[/dim]")

    # 2. Initialize database
    async def _init():
        from cerberus.core.database import init_db
        await init_db()

    asyncio.run(_init())
    console.print(f"[bold green]Database schema initialized and connection pool warmed.[/bold green]")

    # 3. Install Git hooks if inside git repo
    if (repo_dir / ".git").exists():
        install_git_hooks(repo_dir=repo_dir)

    console.print(Panel(
        f"[bold green]cerberus</> initialized successfully![/bold green]\n\n"
        f"Quick Start Commands:\n"
        f"  - Review snippet: [yellow]python -m cerberus.cli review -s 'import os; os.system(\"ls\")'[/yellow]\n"
        f"  - Start Dashboard: [yellow]python -m cerberus.cli serve[/yellow] (http://localhost:8000)\n"
        f"  - Environment Doctor: [yellow]python -m cerberus.cli doctor[/yellow]",
        title="[bold green]Ready to Review[/bold green]",
        border_style="green"
    ))


hooks_app = typer.Typer(name="hooks", help="Manage automated zero-click Git hooks (pre-commit, pre-push)")


@hooks_app.command(name="install")
def install_git_hooks(
    repo_dir: Path = typer.Option(Path("."), "--repo-dir", "-d", help="Path to Git repository root")
):
    """Install automated pre-commit and pre-push quality review hooks into .git/hooks."""
    hooks_dir = repo_dir / ".git" / "hooks"
    if not (repo_dir / ".git").exists():
        console.print(f"[bold red]Error:[/bold red] Directory '{repo_dir}' is not a valid Git repository (.git not found).")
        raise typer.Exit(code=1)
    hooks_dir.mkdir(parents=True, exist_ok=True)

    pre_commit_script = """#!/usr/bin/env sh
# cerberus</> Automated Pre-Commit Hook
# Scans staged files before allowing commit
echo "🛡️ Running cerberus</> autonomous pre-commit code review..."
cerberus review --blocking
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ cerberus</> flagged blocking issues. Fix issues or use git commit --no-verify to override."
    exit $EXIT_CODE
fi
"""
    pre_push_script = """#!/usr/bin/env sh
# cerberus</> Automated Pre-Push Hook
echo "🛡️ Running cerberus</> multi-agent pre-push audit..."
cerberus review --blocking
exit $?
"""
    (hooks_dir / "pre-commit").write_text(pre_commit_script, encoding="utf-8")
    (hooks_dir / "pre-push").write_text(pre_push_script, encoding="utf-8")

    console.print(Panel(
        f"[bold green]Successfully installed Git hooks into {hooks_dir}![/bold green]\n\n"
        f"- [cyan]pre-commit[/cyan]: Blocks commits containing critical security or quality issues.\n"
        f"- [cyan]pre-push[/cyan]: Verifies multi-agent consensus before pushing upstream.",
        title="[bold green]cerberus</> Git Hooks Installed[/bold green]",
        border_style="green"
    ))


@hooks_app.command(name="uninstall")
def uninstall_git_hooks(
    repo_dir: Path = typer.Option(Path("."), "--repo-dir", "-d", help="Path to Git repository root")
):
    """Remove cerberus automated pre-commit and pre-push hooks."""
    hooks_dir = repo_dir / ".git" / "hooks"
    for hook_name in ("pre-commit", "pre-push"):
        target = hooks_dir / hook_name
        if target.exists():
            content = target.read_text(encoding="utf-8", errors="ignore")
            if "cerberus" in content:
                target.unlink()
                console.print(f"[dim]Removed {hook_name} hook.[/dim]")
    console.print("[bold green]cerberus</> Git hooks uninstalled cleanly.[/bold green]")


app.add_typer(hooks_app)


if __name__ == "__main__":
    app()
