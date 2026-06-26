"""Slash command: /pending — show unanswered questions."""

from __future__ import annotations

from datetime import datetime, timezone

import discord
from discord import app_commands

from automation.storage.database import Database


_db: Database | None = None


def set_database(db: Database) -> None:
    global _db
    _db = db


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="pending", description="Show unanswered questions awaiting human input")
    async def pending_cmd(interaction: discord.Interaction) -> None:
        if not _db:
            await interaction.response.send_message("Database not available.", ephemeral=True)
            return

        pending = _db.get_pending_questions()
        sent = _db.get_sent_questions()
        all_active = pending + sent

        if not all_active:
            await interaction.response.send_message(
                "No pending questions.", ephemeral=True,
            )
            return

        lines = []
        now = datetime.now(timezone.utc)
        for q in all_active:
            try:
                asked = datetime.fromisoformat(q.created_at)
                delta = now - asked
                mins = int(delta.total_seconds() / 60)
                ago = f"{mins} min ago" if mins < 60 else f"{mins // 60}h ago"
            except (ValueError, TypeError):
                ago = "unknown"

            qtype = f"[{q.question_type}] " if q.question_type else ""
            status = "awaiting answer" if q.status.value == "sent" else "queued"
            lines.append(f"**#{q.id}** {qtype}{q.question[:80]}\n    {ago} \u2014 {status}")

        embed = discord.Embed(
            title=f"Pending Questions ({len(all_active)})",
            description="\n".join(lines)[:4096],
            color=discord.Color.yellow(),
        )
        await interaction.response.send_message(embed=embed)
