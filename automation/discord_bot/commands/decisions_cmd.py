"""Slash command: /decisions — show recent decisions from DECISIONS.md."""

from __future__ import annotations

import re

import discord
from discord import app_commands

from automation.agents.decisions import read_decisions


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="decisions", description="Show recent decisions from DECISIONS.md")
    @app_commands.describe(count="Number of recent decisions to show (default 5)")
    async def decisions_cmd(interaction: discord.Interaction, count: int = 5) -> None:
        content = read_decisions()
        if not content:
            await interaction.response.send_message(
                "No `DECISIONS.md` found or it is empty.", ephemeral=True,
            )
            return

        # Parse decision blocks (## headings).
        blocks = re.split(r"(?=^## )", content, flags=re.MULTILINE)
        decision_blocks = [b.strip() for b in blocks if b.strip() and b.strip().startswith("## ")]

        if not decision_blocks:
            await interaction.response.send_message(
                "No decisions recorded yet.", ephemeral=True,
            )
            return

        # Show the most recent N.
        recent = decision_blocks[-count:]
        recent.reverse()  # Most recent first.

        lines = []
        for i, block in enumerate(recent, 1):
            # Extract title and date.
            title_match = re.match(r"## (.+)", block)
            title = title_match.group(1).strip() if title_match else "Untitled"
            date_match = re.search(r"\*\*Date:\*\*\s*(.+)", block)
            date_str = date_match.group(1).strip() if date_match else ""
            date_suffix = f" ({date_str})" if date_str else ""
            lines.append(f"**{i}.** {title}{date_suffix}")

        embed = discord.Embed(
            title=f"Recent Decisions ({len(recent)})",
            description="\n".join(lines)[:4096],
            color=discord.Color.purple(),
        )
        await interaction.response.send_message(embed=embed)
