"""Discord UI components — interactive buttons and modals for answering questions."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable, Coroutine

import discord

from automation.storage.models import Answer, Question

logger = logging.getLogger("automation.discord_bot.views")


class QuestionView(discord.ui.View):
    """Persistent view with option buttons + a freeform reply button.

    This view survives bot restarts because we use custom_id on every component
    and re-register the view on startup via bot.add_view().
    """

    def __init__(
        self,
        question: Question,
        on_answer: Callable[[Question, Answer], Coroutine],
    ):
        # timeout=None makes the view persistent (never expires).
        super().__init__(timeout=None)
        self.question = question
        self.on_answer = on_answer

        # Add a button for each option.
        for opt in question.options_list():
            btn = OptionButton(
                label=f"{opt['label']}: {opt['text'][:70]}",
                custom_id=f"q{question.id}_opt_{opt['label']}",
                option_label=opt["label"],
                option_text=opt["text"],
                parent_view=self,
            )
            self.add_item(btn)

        # Always add a freeform reply button.
        freeform_btn = FreeformButton(
            custom_id=f"q{question.id}_freeform",
            parent_view=self,
        )
        self.add_item(freeform_btn)


class OptionButton(discord.ui.Button):
    """Button for a specific option (A, B, C, ...)."""

    def __init__(
        self,
        label: str,
        custom_id: str,
        option_label: str,
        option_text: str,
        parent_view: QuestionView,
    ):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=label[:80],
            custom_id=custom_id,
        )
        self.option_label = option_label
        self.option_text = option_text
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        answer = Answer(
            question_id=self.parent_view.question.id,
            answer_text=self.option_text,
            answer_option=self.option_label,
            discord_user_id=str(interaction.user.id),
            discord_username=str(interaction.user),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Disable all buttons after selection.
        for item in self.parent_view.children:
            item.disabled = True
        await interaction.response.edit_message(view=self.parent_view)

        logger.info(
            "Option selected: q=%d opt=%s by=%s",
            self.parent_view.question.id, self.option_label, interaction.user,
        )
        await self.parent_view.on_answer(self.parent_view.question, answer)


class FreeformButton(discord.ui.Button):
    """Button that opens a modal for a freeform text response."""

    def __init__(self, custom_id: str, parent_view: QuestionView):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="Reply with custom answer",
            custom_id=custom_id,
        )
        self.parent_view = parent_view

    async def callback(self, interaction: discord.Interaction):
        modal = FreeformModal(self.parent_view)
        await interaction.response.send_modal(modal)


class FreeformModal(discord.ui.Modal):
    """Modal for typing a freeform response."""

    answer_input = discord.ui.TextInput(
        label="Your answer",
        style=discord.TextStyle.paragraph,
        placeholder="Type your decision or response here...",
        required=True,
        max_length=2000,
    )

    def __init__(self, parent_view: QuestionView):
        super().__init__(title="Respond to Question")
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        answer = Answer(
            question_id=self.parent_view.question.id,
            answer_text=self.answer_input.value,
            answer_option="",
            discord_user_id=str(interaction.user.id),
            discord_username=str(interaction.user),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Disable buttons.
        for item in self.parent_view.children:
            item.disabled = True

        await interaction.response.edit_message(view=self.parent_view)

        logger.info(
            "Freeform answer: q=%d by=%s text=%s",
            self.parent_view.question.id, interaction.user,
            self.answer_input.value[:80],
        )
        await self.parent_view.on_answer(self.parent_view.question, answer)


def make_persistent_view(
    question: Question,
    on_answer: Callable[[Question, Answer], Coroutine],
) -> QuestionView:
    """Create a QuestionView that can be re-registered on bot restart."""
    return QuestionView(question=question, on_answer=on_answer)
