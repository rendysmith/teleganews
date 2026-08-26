> 🌐 **English** · [Русский](README.ru.md)

# 📰 TelegaNews

Telegram bot that automatically collects news from Telegram channels, stores them in a vector database (PostgreSQL + pgvector), and generates an AI summary for a chosen topic and time period on user request.

**The idea in a nutshell:** a background parser scans channels every hour, turns every post into an embedding vector (local model `cointegrated/rubert-tiny2`, 312 dimensions) and stores it in the database. The bot user picks a topic and a period (14 or 30 days) — the bot finds semantically close posts in the DB (cosine similarity via an HNSW index), packs them into a context block and sends it to an external LLM proxy, which writes a coherent summary with links back to the original posts.

---

## Features

- 🤖 Telegram bot built on aiogram 3: pick topic → pick period → get a summary
- 📡 Parsing Telegram channels through user accounts (Pyrogram), session rotation
- 🛡 Flood-ban handling: `block_time` temporarily removes an account from rotation
- 🗃 DB-level deduplication (`UNIQUE (channel, message_id)`)
- 🧹 Automatic cleanup of records older than 60 days
- 🔍 Semantic search: pgvector + HNSW index with cosine metric
- ⚙️ LLM prompts are stored in the database — editable without redeploying
- 🐳 Docker deployment (2 containers) + CI/CD via GitHub Actions

---

## Architecture

```
┌──────────────┐        ┌─────────────────────┐        ┌───────────────┐
│  Parser      │ ─────► │  PostgreSQL         │ ◄───── │  Bot          │
│  (Pyrogram + │        │  + pgvector         │        │  (aiogram 3)  │
│   APScheduler│        │  schema: tg_ai      │        │  + FSM        │
│   every hour)│        └─────────────────────┘        └───────┬───────┘
└──────┬───────┘                                              │
       │  Telegram API (channel parsing)                      │ RAG: vector
       └─────────────────────────────┐                        │ search + context
                                     ▼                        ▼
                          ┌────────────────────────┐  ┌──────────────────┐
                          │  LLM Proxy API         │◄─┤  services/       │
                          │  (external service,    │  │  search_news.py  │
                          │  Basic Auth)           │  │  (LangChain)     │
                          └────────────────────────┘  └──────────────────┘
```

The project consists of three logical parts:

| Component | File | Role |
|---|---|---|
| **Parser** | `parser.py` | Background worker with a scheduler (APScheduler, 1-hour interval). Pulls channels from the DB (max 7 per iteration), parses up to 100 latest messages (30-day window), embeds them and writes to `history`. Also deletes records older than 60 days. |
| **Bot** | `bot.py` | The Telegram bot. Flow: `/start` → pick topic → pick period (14/30 days) → summary generation. State is kept in FSM. |
| **RAG layer** | `services/search_news.py` | Semantic search over `history` (cosine distance to the topic description) and context assembly; a custom LangChain LLM class (`TgProxyLLM`) that talks to the external proxy with retries (3 attempts, exponential backoff) and a 120 s timeout. |

### Data flow

1. **Parser**, every 60 minutes: takes available sessions (`block_time` in the past) and channels not yet checked today (`last_checked_at`).
2. For every message of the channel from the last 30 days it computes an embedding with `rubert-tiny2` and inserts it into `history`. Duplicates (`channel` + `message_id`) are ignored by the database.
3. The **user** presses `/start` — the bot reads the topic list from `topics`.
4. After the period is chosen, the bot takes the topic's full description, finds semantically close posts within N days (`get_context_from_db`), and builds a context block with links of the form `https://t.me/{channel}/{message_id}`.
5. The prompt template is read from the `prompts` table (project `tg_news`); the `{short_history}` (found posts) and `{topic}` (topic description) placeholders are filled in.
6. The LangChain chain (`prompt | llm`) calls the LLM proxy, and the result is shown to the user.

---

## Database

**PostgreSQL** with the **pgvector** extension. Connection settings come from `POSTGRESQL_*` environment variables (see "Environment variables" below). The DB is external to docker-compose (compose only runs the bot and the parser).

All tables live in the `tg_ai` schema, except `prompts`, which is in the `public` schema.

### Tables

#### 📌 `channels` (schema `tg_ai`) — channels to parse

| Column | Type | Description |
|---|---|---|
| `channel_id` | Integer, PK | Auto-increment |
| `channel` | String, unique-index | Channel name (`username`) or invite link (`t.me/+xxxx`) |
| `last_checked_at` | Date, nullable | Date of the last successful check; the parser only takes channels whose date is not today |

**Purpose:** the registry of news sources. `last_checked_at` spreads channel checks across days — at most 7 channels per iteration, the rest wait for the next hour/day.

#### 🔑 `sessions` (schema `tg_ai`) — Telegram accounts used for parsing

| Column | Type | Description |
|---|---|---|
| `user_id` | Integer, PK | Auto-increment |
| `user_name` | String, index | Client name (used as the Pyrogram client `name`) |
| `api_id` / `api_hash` | String | The account's Telegram API keys |
| `session` | String, nullable | Ready Pyrogram session string (Base64). If empty — generated on a local parser run (interactive authorization) |
| `block_time` | Integer, nullable | Unix time until which the account is excluded from rotation (flood ban, error 420) |

**Purpose:** parsing through user accounts allows reading channels without the Bot API and without its channel limits. Sessions are picked at random, and `block_time` lets an account "cool down" after a flood ban.

#### 📋 `topics` (schema `tg_ai`) — bot topics

| Column | Type | Description |
|---|---|---|
| `topic_id` | Integer, PK | Auto-increment |
| `topic` | String, index | Short topic name (shown as a button in the bot) |
| `description` | String | Detailed topic description — used as the vector query to find relevant posts |

**Purpose:** the embedding query is computed from the description (not the short name) — the more detailed the description, the more precise the semantic search.

#### 🧠 `prompts` (schema `public`) — prompt templates

| Column | Type | Description |
|---|---|---|
| `prompt_id` | Integer, PK | Auto-increment |
| `project_name` | String, index | Project identifier (the bot looks up `'tg_news'`) |
| `prompt` | String | Prompt text — **must** contain the `{short_history}` and `{topic}` placeholders |

**Purpose:** prompts are kept in the DB so the LLM behavior (tone, summary structure, citation rules) can be edited without redeploying the bot — just update the row.

#### 📰 `history` (schema `tg_ai`) — posts and their vectors

| Column | Type | Description |
|---|---|---|
| `history_id` | Integer, PK | Auto-increment |
| `date` | DateTime, index | Post publication date |
| `channel` | String, index | Source channel |
| `message_id` | Integer, index | Message ID within the channel (for `t.me/{channel}/{message_id}` links) |
| `message` | String | Post text (or media caption) |
| `message_emb` | `vector(312)` | Text embedding from rubert-tiny2 |
| `created_at` | DateTime | Insert time (set by the DB itself, `server_default=now()`) |

Extra details:
- **HNSW index** `hnsw_idx_history_emb` (`vector_cosine_ops`, m=16, ef_construction=64) — speeds up cosine search on large volumes.
- **`UNIQUE (channel, message_id)`** — DB-level duplicate protection (inserts use `INSERT ... ON CONFLICT DO NOTHING`).
- **Retention:** the parser deletes records with `date` older than 60 days on every iteration.

**Purpose:** this is the "news corpus" for RAG — all semantic search happens against this table only. Vectors let you search by meaning rather than keywords.

### Schema initialization

There is no automatic table creation in the code (`Base.metadata.create_all` is never called) and no alembic migrations, so on first deployment run this manually:

```sql
CREATE EXTENSION IF NOT EXISTS vector;   -- pgvector
CREATE SCHEMA IF NOT EXISTS tg_ai;
```

and create the tables through SQLAlchemy (models live in `models/mdl_tables.py`):

```python
import asyncio
from database.db_loader import engine
from models.mdl_tables import Base

async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

asyncio.run(create_tables())
```

After that, fill in the starting data: channels, topics, the prompt, and at least one session.

---

## Environment variables (.env)

| Variable | Used in | Purpose |
|---|---|---|
| `BOT_TOKEN` | `bot.py` | Telegram bot token (required — the bot won't start without it) |
| `POSTGRESQL_HOST` | `database/db_loader.py` | PostgreSQL host |
| `POSTGRESQL_PORT` | `database/db_loader.py` | PostgreSQL port |
| `POSTGRESQL_DB` | `database/db_loader.py` | Database name |
| `POSTGRESQL_USERNAME` | `database/db_loader.py` | DB user |
| `POSTGRESQL_PASSWORD` | `database/db_loader.py` | DB password |
| `GENERATOR_API_URL` | `services/search_news.py` | LLM proxy URL (has a default: `http://109.107.170.211:8000/api/v1/start_generation`) |
| `LOGIN_GEN` | `services/search_news.py` | Basic Auth login for the LLM proxy |
| `PASS_GEN` | `services/search_news.py` | Basic Auth password for the LLM proxy |
| `BOT_NAME` | `parser.py` | Pyrogram client name used when generating a session (default `my_bot`) |

---

## Installation and running

### Local development

```bash
# 1. Virtual environment and dependencies
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Configuration
cp .env.example .env   # or create .env per the table above

# 3. Prepare the DB (see "Schema initialization")
#    + the embedding model will be downloaded on first run

# 4. Start the parser (on first run it will create a Pyrogram session
#    — an account authorization code will be requested)
python parser.py

# 5. In another terminal — the bot
python bot.py
```

> **Sessions matter:** in Docker, sessions are not generated — the parser only uses ready-made session strings from the DB. So before deploying, obtain a session string via a local `parser.py` run (or standalone — `get_session` in `parser.py`) and put it into the `sessions` table.

### Docker

```bash
# First build the shared base image with dependencies (used by both services)
docker build -f Dockerfile.base -t teleganews-base:latest .

# Then build and start the services
docker compose up -d --build
```

`docker-compose.yml` starts two containers (`telega_bot`, `telega_parser`) on a shared network; both read `.env` and restart on failure (`restart: always`). PostgreSQL stays external.

### Server deployment (GitHub Actions)

The workflow `.github/workflows/deploy.yml` triggers on pushes to the `main` branch (or manually via `workflow_dispatch`):

1. Connects to the VDS over SSH (secrets `VDS_HOST`, `VDS_USER`, `VDS_SSH_KEY`).
2. `git fetch` + `git reset --hard origin/main` (local edits on the server are discarded).
3. Prunes the Docker cache, builds `Dockerfile.base` (dependencies are installed once).
4. `docker compose build && docker compose up -d`.

---

## Using the bot

1. Send `/start` — a keyboard with topics appears (from the `topics` table).
2. Pick a topic — the bot asks for the period: **last 14 days** or **last 30 days**.
3. The bot finds relevant posts and generates a summary (usually 1–2 minutes); the result replaces the waiting message.

If no relevant news exists for the period, the bot says so honestly.

---

## Project structure

```
teleganews/
├── bot.py                    # Telegram bot (aiogram 3): topics → period → summary
├── parser.py                 # Channel parser (Pyrogram + APScheduler + embeddings)
├── models/
│   └── mdl_tables.py         # SQLAlchemy models: prompts, sessions, channels, topics, history
├── database/
│   └── db_loader.py          # asyncpg connection pool + universal CRUD helpers
├── services/
│   └── search_news.py        # RAG: vector search over history + LangChain chain to the LLM proxy
├── core/
│   └── logger.py             # (unused) loguru configuration
├── Dockerfile.base           # Base image: Python 3.12 + dependencies (CPU-only torch)
├── Dockerfile.bot            # Bot image
├── Dockerfile.parser         # Parser image
├── docker-compose.yml        # Orchestrates the bot and the parser
├── requirements.txt          # Python dependencies
└── .github/workflows/deploy.yml  # CI/CD: auto-deploy to VDS on pushes to main
```

---

## Notes and known limitations

- **The embedding model is not baked into the Docker image.** The parser runs in offline mode (`HF_HUB_OFFLINE=1`), but `Dockerfile.base` has no step that downloads `cointegrated/rubert-tiny2` — on a fresh server the parser container will crash at startup. Recommended fix — add to `Dockerfile.base`:
  ```dockerfile
  RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('cointegrated/rubert-tiny2')"
  ```
- **The DB schema is not created automatically** — see "Schema initialization".
- **Bot reply formatting** uses legacy `Markdown`: LLM output containing `*`, `_`, `[` can break Telegram's parsing. If errors occur frequently, switch to HTML or escape MarkdownV2.
- **`prompts` lives in the `public` schema**, the other tables in `tg_ai`. Move it to `tg_ai` if you prefer consistency.
- The prompt in `prompts` must contain the `{short_history}` and `{topic}` placeholders — without them the LangChain chain assembly fails.
