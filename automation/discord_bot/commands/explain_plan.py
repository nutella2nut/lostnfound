"""Slash command: /explain-plan — show current session plan and handoff state."""

from __future__ import annotations

import discord
from discord import app_commands

from automation.agents.handoff import read_handoff
from automation.agents.progress import read_progress


def register(tree: app_commands.CommandTree) -> None:
    @tree.command(name="explain-plan", description="Show current session plan, handoff state, and what's next")
    async def explain_plan_cmd(interaction: discord.Interaction) -> None:
        handoff = read_handoff()
        report = read_progress()

        embed = discord.Embed(title="Current Plan", color=discord.Color.teal())

        if handoff:
            if handoff.current_task:
                embed.add_field(
                    name="This Session",
                    value=handoff.current_task[:1024],
                    inline=False,
                )

            if handoff.completed_this_session:
                items = "\n".join(f"\u2022 {i}" for i in handoff.completed_this_session[:10])
                embed.add_field(name="Done This Session", value=items[:1024], inline=False)

            if handoff.remaining_work:
                items = "\n".join(f"\u2022 {i}" for i in handoff.remaining_work[:10])
                embed.add_field(name="Remaining This Session", value=items[:1024], inline=False)

            if handoff.resume_instructions:
                embed.add_field(
                    name="Handoff Note",
                    value=handoff.resume_instructions[:1024],
                    inline=False,
                )

            embed.set_footer(
                text=f"Session: {handoff.session_id[:12]} | Context: {handoff.context_pct}%",
            )
        else:
            embed.description = "No active session handoff found."

        if report:
            remaining_count = len(report.remaining)
            if remaining_count:
                next_items = report.remaining[:3]
                items = "\n".join(f"\u2022 {i}" for i in next_items)
                embed.add_field(
                    name=f"Overall Remaining ({remaining_count})",
                    value=items[:1024],
                    inline=False,
                )

        await interaction.response.send_message(embed=embed)
