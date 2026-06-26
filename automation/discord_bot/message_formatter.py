"""Format Question objects and agent events as Discord embeds."""

from __future__ import annotations

import discord

from automation.storage.models import AgentEvent, ContextLevel, Question

# Color mapping for question types.
_TYPE_COLORS = {
    "Business": discord.Color.gold(),
    "Product": discord.Color.blue(),
    "Architecture": discord.Color.purple(),
    "Security": discord.Color.red(),
    "External Resource": discord.Color.orange(),
}


def format_question_embed(q: Question) -> discord.Embed:
    """Build a rich embed for a question."""
    color = _TYPE_COLORS.get(q.question_type, discord.Color.greyple())
    title = f"{q.question_type or 'Question'}" if q.question_type else "Question"

    embed = discord.Embed(
        title=title,
        description=q.question,
        color=color,
    )

    if q.context:
        embed.add_field(name="Context", value=_truncate(q.context, 1024), inline=False)

    # Options
    options = q.options_list()
    if options:
        opts_text = "\n".join(
            f"**{o['label']}:** {o['text']}" for o in options
        )
        embed.add_field(name="Options", value=_truncate(opts_text, 1024), inline=False)

    if q.recommended:
        embed.add_field(name="Recommended", value=q.recommended, inline=True)

    if q.confidence:
        embed.add_field(name="Confidence", value=q.confidence, inline=True)

    if q.rationale:
        embed.add_field(name="Rationale", value=_truncate(q.rationale, 1024), inline=False)

    if q.expected_impact:
        embed.add_field(name="Expected Impact", value=_truncate(q.expected_impact, 1024), inline=False)

    embed.set_footer(text=f"Project: {q.project_slug} | Question #{q.id}")
    return embed


def format_answer_confirmation(q: Question, answer_text: str, username: str) -> discord.Embed:
    """Build a confirmation embed after an answer is received."""
    embed = discord.Embed(
        title="Answer Recorded",
        description=f"**Q:** {_truncate(q.question, 200)}",
        color=discord.Color.green(),
    )
    embed.add_field(name="Answer", value=_truncate(answer_text, 1024), inline=False)
    embed.add_field(name="Answered by", value=username, inline=True)
    embed.set_footer(text=f"Question #{q.id} | Claude Code will resume automatically")
    return embed


# ── Event embeds ──


def format_progress_embed(event: AgentEvent) -> discord.Embed:
    """Build an embed for a progress_update event."""
    task = event.data.get("task", "")
    pct = event.data.get("progress_pct", "")
    desc = task or "Progress update"
    if pct:
        desc += f" ({pct}%)"
    embed = discord.Embed(
        title="\U0001f4ca Progress Update",
        description=desc,
        color=discord.Color.blue(),
    )
    embed.set_footer(text=f"Session: {event.session_id[:12]}")
    return embed


def format_context_checkpoint_embed(level: ContextLevel, action: str) -> discord.Embed:
    """Build an embed for a context threshold notification."""
    color_map = {
        "checkpoint": discord.Color.blue(),
        "handoff": discord.Color.gold(),
        "wrapup": discord.Color.red(),
    }
    title_map = {
        "checkpoint": f"\U0001f4be Context at {level.pct}% \u2014 Checkpoint Saved",
        "handoff": f"\u26a0\ufe0f Context at {level.pct}% \u2014 Handoff Draft Ready",
        "wrapup": f"\U0001f6d1 Context at {level.pct}% \u2014 Session Wrapping Up",
    }
    desc_map = {
        "checkpoint": "PROJECT_CONTEXT.md has been saved. Session can continue.",
        "handoff": "SESSION_HANDOFF.md draft generated. Consider wrapping up the current task.",
        "wrapup": "SESSION_HANDOFF.md finalized. Agent will complete current task and exit.",
    }
    embed = discord.Embed(
        title=title_map.get(action, f"Context at {level.pct}%"),
        description=desc_map.get(action, ""),
        color=color_map.get(action, discord.Color.greyple()),
    )
    if level.session_id:
        embed.set_footer(text=f"Session: {level.session_id[:12]}")
    return embed


def format_session_start_embed(event: AgentEvent) -> discord.Embed:
    """Build an embed for session_start."""
    embed = discord.Embed(
        title="\u25b6\ufe0f Session Started",
        description=f"Session `{event.session_id[:12]}` has begun.",
        color=discord.Color.green(),
    )
    return embed


def format_session_end_embed(event: AgentEvent) -> discord.Embed:
    """Build an embed for session_end."""
    reason = event.data.get("reason", "completed")
    final_pct = event.data.get("final_pct", "")
    desc = f"Session `{event.session_id[:12]}` has ended."
    if reason:
        desc += f"\nReason: {reason}"
    if final_pct:
        desc += f"\nFinal context: {final_pct}%"
    embed = discord.Embed(
        title="\u23f9\ufe0f Session Ended",
        description=desc,
        color=discord.Color.dark_grey(),
    )
    return embed


def format_error_embed(event: AgentEvent) -> discord.Embed:
    """Build an embed for an error event."""
    msg = event.data.get("message", "An error occurred")
    embed = discord.Embed(
        title="\u26a0\ufe0f Error",
        description=_truncate(msg, 4096),
        color=discord.Color.red(),
    )
    embed.set_footer(text=f"Session: {event.session_id[:12]}")
    return embed


def format_milestone_embed(event: AgentEvent) -> discord.Embed:
    """Build an embed for a milestone event."""
    milestone = event.data.get("milestone", "Milestone reached")
    embed = discord.Embed(
        title="\U0001f3c6 Milestone",
        description=milestone,
        color=discord.Color.gold(),
    )
    embed.set_footer(text=f"Session: {event.session_id[:12]}")
    return embed


def format_event_embed(event: AgentEvent) -> discord.Embed:
    """Route an event to the appropriate formatter."""
    formatters = {
        "progress_update": format_progress_embed,
        "session_start": format_session_start_embed,
        "session_end": format_session_end_embed,
        "error": format_error_embed,
        "milestone": format_milestone_embed,
    }
    formatter = formatters.get(event.type)
    if formatter:
        return formatter(event)
    # Fallback.
    embed = discord.Embed(
        title=event.type.replace("_", " ").title(),
        description=str(event.data)[:4096],
        color=discord.Color.greyple(),
    )
    return embed


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
