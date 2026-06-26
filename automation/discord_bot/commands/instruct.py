"""Slash command: /instruct — send a freeform instruction to the agent."""

from __future__ import annotations

import logging

import discord
from discord import app_commands

from automation import config
from automation.providers.base import InstructionProvider
from automation.storage.database import Database
from automation.storage.models import Instruction

logger = logging.getLogger("automation.discord_bot.commands.instruct")

_provider: InstructionProvider | None = None
_db: Database | None = None


def set_dependencies(provider: InstructionProvider, db: Database) -> None:
    global _provider, _db
    _provider = provider
    _db = db


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="instruct", description="Send a freeform instruction to the running agent")
    @app_commands.describe(message="The instruction to send to the agent")
    async def instruct_cmd(interaction: discord.Interaction, message: str) -> None:
        if not _provider or not _db:
            await interaction.response.send_message("Not configured.", ephemeral=True)
            return

        instr = Instruction(
            project_slug=config.PROJECT_SLUG,
            instruction_text=message,
            discord_user_id=str(interaction.user.id),
            discord_username=str(interaction.user),
        )

        # Write via provider (file) and persist in DB.
        _provider.submit(instr)
        _db.insert_instruction(instr)

        embed = discord.Embed(
            title="Instruction Queued",
            description=message[:2000],
            color=discord.Color.blue(),
        )
        embed.set_footer(text=f"ID: {instr.id} | Will be applied at next task boundary")
        await interaction.response.send_message(embed=embed)
        logger.info("Instruction queued: %s by %s", instr.id, interaction.user)
