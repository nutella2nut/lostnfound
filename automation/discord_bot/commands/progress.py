"""Slash command: /progress — show PROJECT_PROGRESS.md summary."""

from __future__ import annotations

import discord
from discord import app_commands

from automation.agents.progress import read_progress


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="progress", description="Show project progress summary")
    async def progress_cmd(interaction: discord.Interaction) -> None:
        report = read_progress()
        if report is None:
            await interaction.response.send_message(
                "No `PROJECT_PROGRESS.md` found.", ephemeral=True,
            )
            return

        embed = discord.Embed(title="Project Progress", color=discord.Color.blue())

        embed.add_field(
            name="Counts",
            value=(
                f"**Completed:** {len(report.completed)}\n"
                f"**In Progress:** {len(report.in_progress)}\n"
                f"**Remaining:** {len(report.remaining)}\n"
                f"**Known Issues:** {len(report.known_issues)}\n"
                f"**Tech Debt:** {len(report.technical_debt)}"
            ),
            inline=False,
        )

        if report.completed:
            recent = report.completed[-5:]
            items = "\n".join(f"\u2022 {i}" for i in recent)
            label = "Recent Completions" if len(report.completed) > 5 else "Completed"
            embed.add_field(name=label, value=items[:1024], inline=False)

        if report.in_progress:
            items = "\n".join(f"\u2022 {i}" for i in report.in_progress)
            embed.add_field(name="In Progress", value=items[:1024], inline=False)

        await interaction.response.send_message(embed=embed)
