"""Shared display constants for HistoryWidget and ActiveWidget."""

from hud.colors import SPAN_COLORS  # noqa: F401 — re-exported for consumers who want the palette without importing from hud.colors directly


def escape(s: str) -> str:
    """Escape all [ characters so Rich never interprets s as markup."""
    return s.replace("[", "\\[")

TYPE_BADGE = {
    "agent":    "[bold blue]agent[/bold blue]",
    "subagent": "[blue]subagent[/blue]",
    "tool":     "[green]tool[/green]",
    "ok":       "[green]ok[/green]",
    "err":      "[red]ERR[/red]",
    "skill":    "[magenta]skill[/magenta]",
    "stop":     "[dim]─ stop ─[/dim]",
}

# PENDING_BADGE shows lighter variants during active execution.
# Nested ToolEvents (depth>0) use PENDING_BADGE["tool"] with arrow prefix.
PENDING_BADGE = {
    "agent":    "[bold blue]…[/bold blue]",
    "subagent": "[blue]…[/blue]",
    "tool":     "[yellow]…[/yellow]",
    "sub":      "[cyan]…[/cyan]",
    "skill":    "[magenta]…[/magenta]",
}


def bold(s: str) -> str:
    """Wrap a string in bold Rich markup, safely escaping any markup characters."""
    return f"[bold]{escape(s)}[/bold]"


def span_prefix(span_color: str | None, depth: int = 0) -> str:
    """Colored gutter prefix for a history line.

    None span  → ""
    depth 0    → bright single │:  "[{color}]│[/{color}] "
    depth > 0  → dim multi │:      "[dim {color}]{'│'*(depth+1)}[/dim {color}] "

    Dim indicates child span; same color = same root ancestor.
    """
    if not span_color:
        return ""
    gutter = "│" * (depth + 1)
    if depth == 0:
        return f"[{span_color}]{gutter}[/{span_color}] "
    return f"[dim {span_color}]{gutter}[/dim {span_color}] "

def badge_and_label(tool_name: str, depth: int) -> tuple[str, str]:
    """Return (PENDING_BADGE key, display label) for a pending entry."""
    if tool_name == "Agent":
        key = "agent" if depth == 0 else "subagent"
        return key, key
    if tool_name == "Skill":
        return "skill", "skill"
    return ("sub" if depth > 0 else "tool"), tool_name


def context_display_name(context_label: str | None) -> str:
    """Strip type prefix from context_label, returning the bare name."""
    if not context_label:
        return ""
    for prefix in ("agent:", "skill:"):
        if context_label.startswith(prefix):
            return context_label[len(prefix):]
    return context_label

