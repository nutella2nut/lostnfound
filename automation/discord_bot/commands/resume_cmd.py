"""Slash command: /resume — clear the pause signal."""

from __future__ import annotations

import logging

import discord
from discord import app_commands

from automation.providers.base import InstructionProvider

logger = logging.getLogger("automation.discord_bot.commands.resume")

_provider: InstructionProvider | None = None


def set_provider(provider: InstructionProvider) -> None:
    global _provider
    _provider = provider


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="resume", description="Resume a paused agent")
    async def resume_cmd(interaction: discord.Interaction) -> None:
        if not _provider:
            await interaction.response.send_message("Not configured.", ephemeral=True)
            return

        if not _provider.is_paused():
            await interaction.response.send_message(
                "Agent is not paused.", ephemeral=True,
            )
            return

        _provider.clear_pause()
        logger.info("Resume signal sent by %s", interaction.user)

        embed = discord.Embed(
            title="\u25b6\ufe0f Agent Resumed",
            description="The pause signal has been cleared. The agent will continue.",
            color=discord.Color.green(),
        )
        await interaction.response.send_message(embed=embed)
