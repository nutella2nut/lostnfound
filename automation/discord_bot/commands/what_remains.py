"""Slash command: /what-remains — show remaining work."""

from __future__ import annotations

import discord
from discord import app_commands

from automation.agents.progress import read_progress


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="what-remains", description="Show remaining work items")
    async def what_remains_cmd(interaction: discord.Interaction) -> None:
        report = read_progress()
        if report is None:
            await interaction.response.send_message(
                "No `PROJECT_PROGRESS.md` found.", ephemeral=True,
            )
            return

        if not report.remaining:
            await interaction.response.send_message(
                "No remaining work items found.", ephemeral=True,
            )
            return

        items = "\n".join(f"{i+1}. {item}" for i, item in enumerate(report.remaining))

        embed = discord.Embed(
            title=f"Remaining Work ({len(report.remaining)})",
            description=items[:4096],
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed)
