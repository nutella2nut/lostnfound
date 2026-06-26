"""Dashboard channel management — maintains a pinned live-status embed.

Creates a #claude-dashboard channel and pins a single status embed.
The embed is edited in-place on every state change, rate-limited to
avoid Discord API throttling.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import discord

from automation import config
from automation.agents import progress as progress_mod
from automation.agents import handoff as handoff_mod
from automation.storage.models import ContextLevel

logger = logging.getLogger("automation.discord_bot.dashboard")


class Dashboard:
    """Manages the pinned dashboard embed in #claude-dashboard."""

    def __init__(self, guild: discord.Guild):
        self._guild = guild
        self._channel: Optional[discord.TextChannel] = None
        self._message: Optional[discord.Message] = None
        self._last_update: float = 0.0
        self._pending_update: bool = False
        self._update_lock = asyncio.Lock()
        # Cached state for the embed.
        self._context_level: Optional[ContextLevel] = None
        self._session_state: str = "idle"
        self._session_id: str = ""
        self._session_started: str = ""
        self._pending_questions: int = 0
        self._last_decision: str = ""

    async def initialize(self) -> None:
        """Find or create the dashboard channel and pin message."""
        channel_name = config.DASHBOARD_CHANNEL_NAME

        # Look for existing channel.
        for ch in self._guild.text_channels:
            if ch.name == channel_name:
                self._channel = ch
                break

        if not self._channel:
            # Create under the claude-projects category.
            category = None
            cat_name = config.DISCORD_CATEGORY_NAME
            for cat in self._guild.categories:
                if cat.name.lower() == cat_name.lower():
                    category = cat
                    break
            if not category:
                category = await self._guild.create_category(name=cat_name)

            self._channel = await self._guild.create_text_channel(
                name=channel_name,
                category=category,
                topic="Live project dashboard — auto-updated by Claude Code bot",
            )
            logger.info("Created dashboard channel: #%s", channel_name)

        # Look for existing pinned dashboard message.
        pins = await self._channel.pins()
        for pin in pins:
            if pin.author == self._guild.me and pin.embeds:
                self._message = pin
                logger.info("Found existing dashboard message: %d", pin.id)
                break

        if not self._message:
            embed = self._build_embed()
            self._message = await self._channel.send(embed=embed)
            await self._message.pin()
            logger.info("Created and pinned dashboard message: %d", self._message.id)

    def update_context(self, level: ContextLevel) -> None:
        """Update cached context level."""
        self._context_level = level
        if level.session_id:
            self._session_id = level.session_id

    def update_session_state(self, state: str, session_id: str = "", started: str = "") -> None:
        """Update session state info."""
        self._session_state = state
        if session_id:
            self._session_id = session_id
        if started:
            self._session_started = started

    def update_pending_questions(self, count: int) -> None:
        """Update pending question count."""
        self._pending_questions = count

    def update_last_decision(self, decision: str) -> None:
        """Update the last decision text."""
        self._last_decision = decision

    async def refresh(self) -> None:
        """Rebuild and edit the dashboard embed, respecting rate limits."""
        now = time.monotonic()
        if now - self._last_update < config.DASHBOARD_UPDATE_INTERVAL:
            self._pending_update = True
            return

        async with self._update_lock:
            self._pending_update = False
            self._last_update = time.monotonic()

            if not self._channel or not self._message:
                return

            embed = self._build_embed()
            try:
                await self._message.edit(embed=embed)
            except discord.HTTPException as exc:
                logger.warning("Failed to update dashboard: %s", exc)

    async def flush_pending(self) -> None:
        """If an update was rate-limited, push it now."""
        if self._pending_update:
            await self.refresh()

    def _build_embed(self) -> discord.Embed:
        """Build the dashboard embed from cached state."""
        # Read live data from files.
        summary = progress_mod.get_summary()
        current_task = progress_mod.get_current_task() or "(idle)"

        ctx_pct = self._context_level.pct if self._context_level else 0

        state_emoji = {
            "idle": "\u26aa",       # white circle
            "running": "\U0001f535", # blue circle
            "waiting_human": "\U0001f7e1", # yellow circle
            "paused": "\u23f8\ufe0f",      # pause
            "wrapping_up": "\U0001f7e0",   # orange circle
            "completed": "\u2705",         # green check
            "failed": "\u274c",            # red x
        }
        state_display = state_emoji.get(self._session_state, "\u2753") + " " + self._session_state.replace("_", " ").title()

        embed = discord.Embed(
            title="Project Dashboard",
            color=discord.Color.blurple(),
        )

        # Status block.
        status_lines = [
            f"**Status:** {state_display}",
            f"**Context:** {ctx_pct}%",
        ]
        if self._session_id:
            status_lines.append(f"**Session:** `{self._session_id[:12]}`")
        if self._session_started:
            status_lines.append(f"**Started:** {self._session_started}")
        embed.add_field(name="Session", value="\n".join(status_lines), inline=False)

        # Current task.
        embed.add_field(name="Current Task", value=current_task[:1024], inline=False)

        # Progress counts.
        if summary.get("exists"):
            progress_lines = [
                f"\u2705 {summary['completed_count']} completed",
                f"\U0001f504 {summary['in_progress_count']} in progress",
                f"\u2b1c {summary['remaining_count']} remaining",
                f"\u2753 {self._pending_questions} pending questions",
            ]
            embed.add_field(name="Progress", value="\n".join(progress_lines), inline=False)
        else:
            embed.add_field(name="Progress", value="No PROJECT_PROGRESS.md found", inline=False)

        # Last decision.
        if self._last_decision:
            embed.add_field(
                name="Last Decision",
                value=self._last_decision[:1024],
                inline=False,
            )

        embed.set_footer(text=f"Project: {config.PROJECT_SLUG} | Auto-updated")
        return embed

    async def post_notification(self, embed: discord.Embed) -> Optional[discord.Message]:
        """Post a one-off notification to the dashboard channel."""
        if not self._channel:
            return None
        try:
            return await self._channel.send(embed=embed)
        except discord.HTTPException as exc:
            logger.warning("Failed to post dashboard notification: %s", exc)
            return None
