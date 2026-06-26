# Discord Human-in-the-Loop System

A Discord bot that bridges Claude Code agents with human decision-makers. Supports bidirectional communication: agents ask questions and emit progress events; humans answer, send instructions, and monitor via a live dashboard.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Claude Code Agent                         │
│                                                                  │
│  Emits:  questions (submit_question)                             │
│          events (submit_event)                                   │
│          context level (submit_event --context-level)            │
│                                                                  │
│  Reads:  answers (check_answer / state/answers/)                 │
│          instructions (check_instructions / state/instructions/) │
│          pause signal (check_instructions --check-pause)         │
└──────────────┬───────────────────────────────┬──────────────────┘
               │                               │
               ▼                               ▼
      ┌─────────────────┐            ┌──────────────────┐
      │  questions.db   │            │  state/ files    │
      │  (SQLite)       │            │  (filesystem)    │
      └────────┬────────┘            └────────┬─────────┘
               │                               │
               ▼                               ▼
      ┌────────────────────────────────────────────────────┐
      │              Discord Bot (watcher loop)             │
      │                                                     │
      │  Polls:   questions DB (every 3s)                   │
      │           events.jsonl (every 3s)                   │
      │           context_level.json (every 3s)             │
      │                                                     │
      │  Posts to Discord:                                  │
      │    #<project-slug>   — questions, progress, alerts  │
      │    #claude-dashboard — live status embed             │
      │                                                     │
      │  Receives from Discord:                             │
      │    Button clicks     → answers/ files               │
      │    Channel messages  → instructions/ files          │
      │    /instruct         → instructions/ files          │
      │    /pause, /resume   → pause_signal flag            │
      │    Slash commands    → reads .md files, responds    │
      └────────────────────────────────────────────────────┘
               │
               ▼
      ┌────────────────────────────────────────────────────┐
      │                    Discord Server                   │
      │                                                     │
      │  Category: claude-projects                          │
      │    #claude-dashboard    — pinned live status        │
      │    #lost-and-found-system — questions & updates     │
      └────────────────────────────────────────────────────┘
```

### Provider Abstraction

All file-based communication is abstracted behind interfaces:

| Interface | v1 Implementation | Purpose |
|---|---|---|
| `ContextProvider` | `FileContextProvider` | Read/write context window % |
| `EventProvider` | `FileEventProvider` | Emit/consume agent lifecycle events |
| `InstructionProvider` | `FileInstructionProvider` | Send instructions, pause/resume |

Future providers (Redis, IPC, HTTP, sockets) can be added without changing business logic.

### Context Thresholds

| Threshold | Action |
|---|---|
| **50%** | Save `PROJECT_CONTEXT.md` checkpoint |
| **60%** | Generate `SESSION_HANDOFF.md` draft |
| **65%** | Finalize handoff, stop new tasks |

### Project Documents

| File | Purpose |
|---|---|
| `DECISIONS.md` | Append-only decision log |
| `PROJECT_PROGRESS.md` | Completed / In Progress / Remaining |
| `SESSION_HANDOFF.md` | Per-session handoff between agent sessions |
| `PROJECT_CONTEXT.md` | Persistent cross-session project understanding |

### Slash Commands

| Command | Description |
|---|---|
| `/progress` | Show PROJECT_PROGRESS.md summary |
| `/current-task` | Show active in-progress task |
| `/what-remains` | Show remaining work items |
| `/pending` | Show unanswered questions |
| `/decisions [count]` | Show recent decisions |
| `/explain-plan` | Show session plan and handoff state |
| `/instruct <message>` | Send instruction to the agent |
| `/pause` | Pause the agent |
| `/resume` | Resume a paused agent |

## Setup

### 1. Create the Discord Bot

1. Go to [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application**. Name it (e.g., `Claude Code Bot`).
3. Go to **Bot** tab → **Reset Token** → copy the token. This is `DISCORD_BOT_TOKEN`.
4. Under **Privileged Gateway Intents**, enable:
   - **Message Content Intent**
   - **Server Members Intent** (optional)
5. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot Permissions: `Send Messages`, `Embed Links`, `Read Message History`, `Manage Channels`, `Manage Messages`, `Use External Emojis`
6. Copy the generated URL and open it to invite the bot to your server.

### 2. Get the Guild (Server) ID

1. In Discord: **User Settings → Advanced → Developer Mode** → ON.
2. Right-click your server name → **Copy Server ID**. This is `DISCORD_GUILD_ID`.

### 3. Configure Environment

```bash
cd automation
cp .env.example .env
# Edit .env with your values
```

### 4. Install Dependencies

```bash
pip install -r automation/requirements.txt
```

### 5. Start the Bot

```bash
cd /path/to/LostAndFoundSystem
export $(grep -v '^#' automation/.env | xargs)
python -m automation
```

The bot will:
1. Connect to Discord and sync slash commands.
2. Create `#claude-dashboard` with a pinned status embed.
3. Find or create the project channel (e.g., `#lost-and-found-system`).
4. Start polling for questions, events, and context level.
5. Recover unanswered questions from previous sessions.

## Usage

### Agent Side: Submitting Questions

```bash
# From a file containing agent output:
python -m automation.submit_question --file agent_output.txt

# With explicit fields:
python -m automation.submit_question \
  --type "Business" \
  --question "Should we use Stripe or Paddle?" \
  --options "A:Stripe,B:Paddle" \
  --recommended "A"
```

### Agent Side: Emitting Events

```bash
# Progress update:
python -m automation.submit_event --type progress_update \
  --session abc123 --data '{"task": "Implemented OAuth", "progress_pct": 40}'

# Update context level:
python -m automation.submit_event --context-level 52 --session abc123

# Session lifecycle:
python -m automation.submit_event --type session_start --session abc123
python -m automation.submit_event --type session_end --session abc123
```

### Agent Side: Checking for Instructions

```bash
# Check for pending instructions:
python -m automation.check_instructions

# JSON output:
python -m automation.check_instructions --json --acknowledge

# Check pause state:
python -m automation.check_instructions --check-pause
```

### Agent Side: Checking for Answers

```bash
# Check a specific question:
python -m automation.check_answer --id 42

# Block until answered:
python -m automation.check_answer --id 42 --wait --timeout 3600
```

### Discord Side

Questions appear as rich embeds with interactive buttons. Users can:
- Click option buttons to select a predefined answer.
- Click "Reply with custom answer" for freeform text.
- **Type natural language messages** in any project channel — they are automatically queued as instructions for the agent. The bot confirms receipt with a checkmark reaction.
- Use slash commands (`/progress`, `/pending`, `/instruct`, etc.).
- View the live dashboard in `#claude-dashboard`.

#### Natural Language Instructions

Any plain-text message in a project channel (e.g., `#lost-and-found-system`) is treated as an instruction to the agent:

```
what are you working on?
prioritize vendor payouts
pause analytics work
```

The bot reacts with a checkmark to confirm the message was queued. The agent picks up instructions at its next task boundary via `check_instructions`.

Messages in `#claude-dashboard` or channels outside the `claude-projects` category are ignored. Bot messages and empty messages are also ignored.

## File Structure

```
automation/
├── __init__.py
├── __main__.py              # Entry point
├── config.py                # Environment-based configuration
├── submit_question.py       # CLI: submit questions
├── check_answer.py          # CLI: check for answers
├── submit_event.py          # CLI: emit agent events
├── check_instructions.py    # CLI: check for instructions
├── requirements.txt
├── .env.example
├── README.md
├── providers/
│   ├── __init__.py
│   ├── base.py              # Abstract interfaces
│   └── file.py              # File-based implementations (v1)
├── discord_bot/
│   ├── __init__.py
│   ├── bot.py               # Main bot with full integration
│   ├── channel_router.py    # Project slug → Discord channel
│   ├── message_formatter.py # Embeds for questions, events, thresholds
│   ├── views.py             # Buttons, modals, persistent views
│   ├── dashboard.py         # Pinned dashboard management
│   └── commands/
│       ├── __init__.py
│       ├── progress.py      # /progress
│       ├── current_task.py  # /current-task
│       ├── what_remains.py  # /what-remains
│       ├── pending.py       # /pending
│       ├── decisions_cmd.py # /decisions
│       ├── explain_plan.py  # /explain-plan
│       ├── instruct.py      # /instruct
│       ├── pause.py         # /pause
│       └── resume_cmd.py    # /resume
├── agents/
│   ├── __init__.py
│   ├── question_parser.py   # Parse WAITING_FOR_DISCORD_REPLY blocks
│   ├── decisions.py         # Read/write DECISIONS.md
│   ├── watcher.py           # Poll DB for pending questions
│   ├── resume.py            # Write answer files, trigger resume
│   ├── progress.py          # Parse PROJECT_PROGRESS.md
│   ├── context_monitor.py   # 50/60/65% threshold logic
│   ├── handoff.py           # SESSION_HANDOFF.md lifecycle
│   └── instruction_handler.py # Process human instructions
├── storage/
│   ├── __init__.py
│   ├── database.py          # SQLite: questions, answers, events, instructions
│   └── models.py            # Data classes and enums
├── state/                   # Runtime data (gitignored, auto-created)
│   ├── .gitkeep
│   ├── questions.db
│   ├── context_level.json
│   ├── events.jsonl
│   ├── answers/
│   ├── instructions/
│   ├── instruction_acks/
│   └── handoffs/
└── tests/
    ├── __init__.py
    ├── test_models.py
    ├── test_providers.py
    ├── test_progress.py
    ├── test_handoff.py
    ├── test_context_monitor.py
    └── test_database.py
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DISCORD_BOT_TOKEN` | Yes | — | Bot token from Discord Developer Portal |
| `DISCORD_GUILD_ID` | Yes | — | Server ID where the bot operates |
| `DISCORD_CATEGORY_NAME` | No | `claude-projects` | Category for project channels |
| `DASHBOARD_CHANNEL_NAME` | No | `claude-dashboard` | Dashboard channel name |
| `CONTEXT_THRESHOLD_CHECKPOINT` | No | `50` | Context % for checkpoint |
| `CONTEXT_THRESHOLD_HANDOFF` | No | `60` | Context % for handoff draft |
| `CONTEXT_THRESHOLD_WRAPUP` | No | `65` | Context % for session wrap-up |
| `RESUME_ENABLED` | No | `true` | Auto-resume Claude Code on answer |
| `RESUME_COMMAND` | No | — | Custom resume shell command |
| `POLL_INTERVAL` | No | `3` | Seconds between poll cycles |
| `DASHBOARD_UPDATE_INTERVAL` | No | `5` | Min seconds between dashboard edits |
| `LOG_LEVEL` | No | `INFO` | Logging level |

## Running Tests

```bash
cd /path/to/LostAndFoundSystem
python -m pytest automation/tests/ -v
```

## Troubleshooting

### Bot doesn't connect
- Verify `DISCORD_BOT_TOKEN` is correct.
- Ensure the bot is invited to the server with the right scopes (`bot`, `applications.commands`).

### Slash commands not appearing
- The bot syncs commands on startup. Check logs for sync errors.
- Try kicking and re-inviting the bot.
- Ensure `applications.commands` scope was included in the OAuth2 URL.

### Events not showing up
- Verify events are being emitted: `cat automation/state/events.jsonl`
- Check `context_level.json` exists: `cat automation/state/context_level.json`

### Dashboard not updating
- Check logs for "Dashboard initialization failed" errors.
- Ensure the bot has `Manage Channels` and `Manage Messages` permissions.

### Buttons stopped working after restart
- The bot re-registers persistent views on startup automatically.
- If buttons on old messages don't work, the question may already be answered.

## Adding Custom Providers

To replace file-based communication with Redis, IPC, or another transport:

1. Create a new module (e.g., `providers/redis.py`).
2. Implement the interfaces from `providers/base.py`:
   - `ContextProvider` — `read_level()`, `write_level()`
   - `EventProvider` — `emit()`, `read_new()`
   - `InstructionProvider` — `submit()`, `check_pending()`, `acknowledge()`, `write_pause()`, `clear_pause()`, `is_paused()`
3. Inject the new providers in `bot.py` instead of the `File*` providers.

No other code needs to change.
