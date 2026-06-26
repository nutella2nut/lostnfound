"""Route projects to Discord channels.

Auto-creates channels under a category if they don't exist.
Caches channel references to avoid repeated API calls.
"""

from __future__ import annotations

import logging
from typing import Optional

import discord

from automation import config

logger = logging.getLogger("automation.discord_bot.router")

# In-memory cache: project_slug -> discord.TextChannel
_channel_cache: dict[str, discord.TextChannel] = {}


async def get_or_create_channel(
    guild: discord.Guild,
    project_slug: str,
) -> discord.TextChannel:
    """Get the channel for a project, creating it if necessary.

    Channel names follow Discord conventions: lowercase, hyphens, no spaces.
    Channels are created under the configured category.
    """
    # Check cache first.
    if project_slug in _channel_cache:
        ch = _channel_cache[project_slug]
        # Verify channel still exists.
        if guild.get_channel(ch.id):
            return ch
        del _channel_cache[project_slug]

    channel_name = project_slug

    # Look for an existing channel with this name.
    for ch in guild.text_channels:
        if ch.name == channel_name:
            _channel_cache[project_slug] = ch
            logger.info("Found existing channel #%s for project '%s'", ch.name, project_slug)
            return ch

    # Channel doesn't exist — create it under the category.
    category = await _get_or_create_category(guild)
    ch = await guild.create_text_channel(
        name=channel_name,
        category=category,
        topic=f"Claude Code questions for project: {project_slug}",
    )
    _channel_cache[project_slug] = ch
    logger.info("Created channel #%s for project '%s'", ch.name, project_slug)
    return ch


async def _get_or_create_category(guild: discord.Guild) -> Optional[discord.CategoryChannel]:
    """Get or create the category for Claude project channels."""
    category_name = config.DISCORD_CATEGORY_NAME

    for cat in guild.categories:
        if cat.name.lower() == category_name.lower():
            return cat

    cat = await guild.create_category(name=category_name)
    logger.info("Created category '%s'", category_name)
    return cat


def get_project_slug(channel: discord.TextChannel) -> Optional[str]:
    """Return the project slug for a channel, or None if it isn't a project channel.

    A channel is a project channel if it lives under the configured category
    and is not the dashboard channel.
    """
    if channel.name == config.DASHBOARD_CHANNEL_NAME:
        return None
    cat = channel.category
    if cat and cat.name.lower() == config.DISCORD_CATEGORY_NAME.lower():
        return channel.name
    return None


def invalidate_cache(project_slug: str = ""):
    """Clear the channel cache. If slug is given, only clear that entry."""
    if project_slug:
        _channel_cache.pop(project_slug, None)
    else:
        _channel_cache.clear()
