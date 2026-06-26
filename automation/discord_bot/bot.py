"""Main Discord bot — ties together channel routing, question delivery, answer handling,
event processing, context monitoring, dashboard, and slash commands."""

from __future__ import annotations

import asyncio
import logging

import discord
from discord import app_commands

from automation import config
from automation.agents import decisions, watcher
from automation.agents.context_monitor import ContextMonitor
from automation.agents.resume import trigger_resume, write_answer_file, write_resume_message
from automation.discord_bot.channel_router import get_or_create_channel, get_project_slug
from automation.discord_bot.commands import (
    current_task,
    decisions_cmd,
    explain_plan,
    instruct,
    pause,
    pending,
    progress,
    resume_cmd,
    what_remains,
)
from automation.discord_bot.dashboard import Dashboard
from automation.discord_bot.message_formatter import (
    format_answer_confirmation,
    format_context_checkpoint_embed,
    format_event_embed,
    format_question_embed,
)
from automation.discord_bot.views import make_persistent_view
from automation.providers.file import (
    FileContextProvider,
    FileEventProvider,
    FileInstructionProvider,
)
from automation.storage.database import Database
from automation.storage.models import AgentEvent, Answer, ContextLevel, Instruction, Question, QuestionStatus

logger = logging.getLogger("automation.discord_bot")


class ClaudeProjectBot(discord.Client):
    """Discord bot that delivers agent questions, captures answers,
    processes events, monitors context, and maintains a dashboard."""

    def __init__(self, db: Database):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        super().__init__(intents=intents)
        self.db = db
        self._guild: discord.Guild | None = None
        self._dashboard: Dashboard | None = None

        # Providers.
        self._ctx_provider = FileContextProvider(config.STATE_DIR)
        self._event_provider = FileEventProvider(config.STATE_DIR)
        self._instr_provider = FileInstructionProvider(config.STATE_DIR)

        # Context monitor.
        self._context_monitor = ContextMonitor(
            provider=self._ctx_provider,
            on_checkpoint=self._on_context_checkpoint,
            on_handoff=self._on_context_handoff,
            on_wrapup=self._on_context_wrapup,
        )

        # Event cursor for tailing events.jsonl.
        self._event_cursor: int = 0

        # Command tree for slash commands.
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        """Called once when the bot is ready to set up background tasks."""
        # Re-register persistent views for unanswered questions.
        await self._restore_pending_views()

        # Inject dependencies into command modules.
        current_task.set_context_provider(self._ctx_provider)
        pending.set_database(self.db)
        instruct.set_dependencies(self._instr_provider, self.db)
        pause.set_provider(self._instr_provider)
        resume_cmd.set_provider(self._instr_provider)

        # Register slash commands.
        progress.register(self.tree)
        current_task.register(self.tree)
        what_remains.register(self.tree)
        pending.register(self.tree)
        decisions_cmd.register(self.tree)
        explain_plan.register(self.tree)
        instruct.register(self.tree)
        pause.register(self.tree)
        resume_cmd.register(self.tree)

    async def on_ready(self) -> None:
        logger.info("Bot connected as %s (id=%s)", self.user, self.user.id)

        # Resolve the guild.
        if config.DISCORD_GUILD_ID:
            self._guild = self.get_guild(int(config.DISCORD_GUILD_ID))
        if not self._guild and self.guilds:
            self._guild = self.guilds[0]
            logger.warning(
                "DISCORD_GUILD_ID not set or not found — using first guild: %s (%s)",
                self._guild.name, self._guild.id,
            )

        if not self._guild:
            logger.error("No guild available. Invite the bot to a server first.")
            return

        logger.info("Operating in guild: %s (%s)", self._guild.name, self._guild.id)

        # Sync slash commands with Discord.
        # Commands are registered globally; copy them to the guild for instant availability.
        try:
            self.tree.copy_global_to(guild=self._guild)
            synced = await self.tree.sync(guild=self._guild)
            logger.info("Synced %d slash commands to guild", len(synced))
        except Exception:
            logger.exception("Failed to sync slash commands — trying global sync")
            try:
                synced = await self.tree.sync()
                logger.info("Synced %d global slash commands", len(synced))
            except Exception:
                logger.exception("Global command sync also failed")

        # Initialize dashboard.
        self._dashboard = Dashboard(self._guild)
        try:
            await self._dashboard.initialize()
            logger.info("Dashboard initialized")
        except Exception:
            logger.exception("Dashboard initialization failed")
            self._dashboard = None

        # Start background loops.
        self.loop.create_task(
            watcher.poll_pending_questions(self.db, self._deliver_question)
        )
        self.loop.create_task(self._poll_events_loop())
        self.loop.create_task(self._dashboard_flush_loop())

    # ── Question delivery ──

    async def _deliver_question(self, question: Question) -> None:
        """Send a question to the appropriate Discord channel."""
        if not self._guild:
            logger.error("No guild — cannot deliver question id=%d", question.id)
            return

        # Check DECISIONS.md for an existing answer before sending.
        existing = decisions.has_existing_decision(question.question)
        if existing:
            logger.info(
                "Question id=%d already answered in DECISIONS.md — auto-resolving",
                question.id,
            )
            auto_answer = Answer(
                question_id=question.id,
                answer_text=f"[Auto-resolved from DECISIONS.md] {existing[:500]}",
                answer_option="",
                discord_user_id="system",
                discord_username="DECISIONS.md",
            )
            self.db.insert_answer(auto_answer)
            self.db.update_question_status(question.id, QuestionStatus.ANSWERED)
            trigger_resume(question, auto_answer)
            return

        # Check for duplicate.
        dup = self.db.find_duplicate(question.project_slug, question.question)
        if dup and dup.id != question.id:
            logger.info(
                "Duplicate question detected (id=%d matches id=%d) — skipping",
                question.id, dup.id,
            )
            self.db.update_question_status(question.id, QuestionStatus.ANSWERED)
            return

        # Get or create the project channel.
        channel = await get_or_create_channel(self._guild, question.project_slug)

        # Build embed and view.
        embed = format_question_embed(question)
        view = make_persistent_view(question, self._handle_answer)

        msg = await channel.send(
            content=f"**New question from Claude Code** (#{question.id})",
            embed=embed,
            view=view,
        )

        self.db.update_question_status(
            question.id,
            QuestionStatus.SENT,
            discord_message_id=msg.id,
            discord_channel_id=channel.id,
        )
        logger.info("Delivered question id=%d to #%s msg=%d", question.id, channel.name, msg.id)

        # Update dashboard.
        if self._dashboard:
            pending_count = len(self.db.get_pending_questions()) + len(self.db.get_sent_questions())
            self._dashboard.update_pending_questions(pending_count)
            await self._dashboard.refresh()

    # ── Answer handling ──

    async def _handle_answer(self, question: Question, answer: Answer) -> None:
        """Process an answer received from Discord."""
        # Persist the answer.
        self.db.insert_answer(answer)
        self.db.update_question_status(question.id, QuestionStatus.ANSWERED)

        # Update DECISIONS.md.
        title = question.question[:80]
        if answer.answer_option:
            decision_text = f"Option {answer.answer_option}: {answer.answer_text}"
        else:
            decision_text = answer.answer_text
        decisions.append_decision(
            title=title,
            decision_text=decision_text,
            reasoning=question.rationale or "Decided via Discord",
            source=f"user ({answer.discord_username}) via Discord",
            question_type=question.question_type,
        )

        # Send confirmation in Discord.
        if question.discord_channel_id and self._guild:
            channel = self._guild.get_channel(question.discord_channel_id)
            if channel:
                conf_embed = format_answer_confirmation(
                    question, decision_text, answer.discord_username,
                )
                await channel.send(embed=conf_embed)

        # Resume Claude Code.
        write_answer_file(question, answer)
        write_resume_message(question, answer)
        trigger_resume(question, answer)

        # Update dashboard.
        if self._dashboard:
            self._dashboard.update_last_decision(f"{title} ({answer.discord_username})")
            pending_count = len(self.db.get_pending_questions()) + len(self.db.get_sent_questions())
            self._dashboard.update_pending_questions(pending_count)
            self._dashboard.update_session_state("running")
            await self._dashboard.refresh()

        logger.info("Answer processed for question id=%d", question.id)

    # ── Channel message → instruction ──

    async def on_message(self, message: discord.Message) -> None:
        """Treat plain-text messages in project channels as instructions."""
        # Ignore the bot's own messages.
        if message.author == self.user:
            return

        # Ignore DMs.
        if not isinstance(message.channel, discord.TextChannel):
            return

        # Ignore empty messages (e.g. image-only).
        text = message.content.strip()
        if not text:
            return

        # Only act on messages inside a project channel.
        project_slug = get_project_slug(message.channel)
        if project_slug is None:
            return

        # Submit as an instruction.
        instr = Instruction(
            project_slug=project_slug,
            instruction_text=text,
            discord_user_id=str(message.author.id),
            discord_username=str(message.author),
        )
        self._instr_provider.submit(instr)
        self.db.insert_instruction(instr)

        # React to confirm receipt instead of posting an embed (less noisy).
        try:
            await message.add_reaction("\u2705")
        except discord.HTTPException:
            pass

        logger.info(
            "Channel message → instruction %s from %s: %s",
            instr.id, message.author, text[:80],
        )

    # ── Event processing ──

    async def _poll_events_loop(self) -> None:
        """Poll for new agent events and context level changes."""
        logger.info("Event/context poller started — polling every %ds", config.POLL_INTERVAL)
        while True:
            try:
                # Check context level.
                self._context_monitor.check()

                # Read new events.
                new_events, new_cursor = self._event_provider.read_new(self._event_cursor)
                self._event_cursor = new_cursor

                for event in new_events:
                    await self._process_event(event)

            except Exception:
                logger.exception("Event poll error")
            await asyncio.sleep(config.POLL_INTERVAL)

    async def _process_event(self, event: AgentEvent) -> None:
        """Handle a single agent event."""
        logger.info("Processing event: %s (session=%s)", event.type, event.session_id[:12] if event.session_id else "?")

        # Persist to DB.
        self.db.insert_event(event)

        # Post to project channel.
        if self._guild:
            try:
                channel = await get_or_create_channel(self._guild, config.PROJECT_SLUG)
                embed = format_event_embed(event)
                await channel.send(embed=embed)
            except Exception:
                logger.exception("Failed to post event to channel")

        # Update dashboard state from events.
        if self._dashboard:
            if event.type == "session_start":
                self._dashboard.update_session_state(
                    "running",
                    session_id=event.session_id,
                    started=event.timestamp,
                )
            elif event.type == "session_end":
                self._dashboard.update_session_state("completed", session_id=event.session_id)
            elif event.type == "progress_update":
                self._dashboard.update_session_state("running")
            elif event.type == "error":
                pass  # Don't change state on non-fatal errors.
            await self._dashboard.refresh()

    # ── Context threshold callbacks ──

    def _on_context_checkpoint(self, level: ContextLevel) -> None:
        """Called when context crosses the checkpoint threshold (50%)."""
        asyncio.ensure_future(self._post_context_notification(level, "checkpoint"))

    def _on_context_handoff(self, level: ContextLevel) -> None:
        """Called when context crosses the handoff threshold (60%)."""
        asyncio.ensure_future(self._post_context_notification(level, "handoff"))

    def _on_context_wrapup(self, level: ContextLevel) -> None:
        """Called when context crosses the wrapup threshold (65%)."""
        asyncio.ensure_future(self._post_context_notification(level, "wrapup"))

    async def _post_context_notification(self, level: ContextLevel, action: str) -> None:
        """Post a context threshold notification to project channel and dashboard."""
        embed = format_context_checkpoint_embed(level, action)

        if self._guild:
            try:
                channel = await get_or_create_channel(self._guild, config.PROJECT_SLUG)
                await channel.send(embed=embed)
            except Exception:
                logger.exception("Failed to post context notification")

        if self._dashboard:
            self._dashboard.update_context(level)
            if action == "wrapup":
                self._dashboard.update_session_state("wrapping_up")
            await self._dashboard.refresh()
            await self._dashboard.post_notification(embed)

    # ── Dashboard flush loop ──

    async def _dashboard_flush_loop(self) -> None:
        """Periodically flush any rate-limited dashboard updates."""
        while True:
            await asyncio.sleep(config.DASHBOARD_UPDATE_INTERVAL)
            if self._dashboard:
                try:
                    await self._dashboard.flush_pending()
                except Exception:
                    logger.exception("Dashboard flush error")

    # ── State recovery ──

    async def _restore_pending_views(self) -> None:
        """Re-register persistent views for questions that were SENT but not yet answered."""
        sent_questions = self.db.get_sent_questions()
        count = 0
        for q in sent_questions:
            view = make_persistent_view(q, self._handle_answer)
            self.add_view(view, message_id=q.discord_message_id)
            count += 1
        if count:
            logger.info("Restored %d persistent views from previous session", count)
