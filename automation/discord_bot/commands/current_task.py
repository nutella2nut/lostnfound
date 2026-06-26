"""Slash command: /current-task — show what the agent is working on."""

from __future__ import annotations

import discord
from discord import app_commands

from automation.agents.progress import read_progress
from automation.providers.base import ContextProvider


_ctx_provider: ContextProvider | None = None


def set_context_provider(provider: ContextProvider) -> None:
    global _ctx_provider
    _ctx_provider = provider


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="current-task", description="Show the current in-progress task")
    async def current_task_cmd(interaction: discord.Interaction) -> None:
        report = read_progress()
        task = report.in_progress[0] if report and report.in_progress else None

        ctx_info = ""
        if _ctx_provider:
            level = _ctx_provider.read_level()
            if level:
                ctx_info = f"Context: {level.pct}%"
                if level.session_id:
                    ctx_info += f" | Session: `{level.session_id[:12]}`"

        if not task:
            await interaction.response.send_message(
                "No task currently in progress.", ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="Current Task",
            description=task,
            color=discord.Color.green(),
        )
        if ctx_info:
            embed.set_footer(text=ctx_info)

        await interaction.response.send_message(embed=embed)
