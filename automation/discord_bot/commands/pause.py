"""Slash command: /pause — signal the agent to pause."""

from __future__ import annotations

import logging

import discord
from discord import app_commands

from automation.providers.base import InstructionProvider

logger = logging.getLogger("automation.discord_bot.commands.pause")

_provider: InstructionProvider | None = None


def set_provider(provider: InstructionProvider) -> None:
    global _provider
    _provider = provider


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="pause", description="Pause the running agent")
    async def pause_cmd(interaction: discord.Interaction) -> None:
        if not _provider:
            await interaction.response.send_message("Not configured.", ephemeral=True)
            return

        if _provider.is_paused():
            await interaction.response.send_message(
                "Agent is already paused.", ephemeral=True,
            )
            return

        _provider.write_pause()
        logger.info("Pause signal sent by %s", interaction.user)

        embed = discord.Embed(
            title="\u23f8\ufe0f Agent Paused",
            description="The agent will pause at the next task boundary.",
            color=discord.Color.orange(),
        )
        await interaction.response.send_message(embed=embed)
