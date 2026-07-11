# T-Invest Trading Bot

Telegram-controlled intraday trading bot for T-Invest (Tinkoff Invest API): strategy backtesting,
sandbox ("demo") trading, and live production trading, with an optional news-sentiment signal.

## Features

- Backtest any built-in strategy against historical candles (`/backtest`)
- Demo trading via the T-Invest **Sandbox** environment — real quotes, virtual money (`/demo`)
- Live trading via the T-Invest **production** environment, gated behind an explicit
  confirmation and a server-side allowlist (`/trade`)
- News sentiment (NewsAPI headlines scored by the Gemini API) usable as a filter on top of
  any strategy - no local ML runtime, so it runs fine on a small/low-RAM server
- Multi-user: each Telegram user supplies their own T-Invest tokens, stored encrypted at rest

## Run with Docker (recommended for a server)

1. Copy `.env.example` to `.env` and fill in `TELEGRAM_BOT_TOKEN`, `MASTER_ENCRYPTION_KEY`,
   `NEWSAPI_KEY`, and `GEMINI_API_KEY` (free, from https://aistudio.google.com/apikey - see
   step 2 below for how to generate the encryption key). Leave `REAL_TRADING_ALLOWLIST` empty
   for now.

   By default, no T-Invest token goes in `.env` - each Telegram user supplies their own
   Sandbox/Production token straight to the bot via `/start`, and it's encrypted and stored
   per-user. **For single-user setups**, you can skip that chat flow entirely: set
   `OWNER_TELEGRAM_ID` (find yours by messaging @userinfobot) plus `TINKOFF_SANDBOX_TOKEN`
   and/or `TINKOFF_PRODUCTION_TOKEN` in `.env`, and the bot loads them for you on every
   startup - `/backtest`, `/demo`, `/trade` work immediately without ever messaging a token
   to the bot.

2. Build and start:

   ```bash
   docker compose up -d --build
   ```

   `docker-compose.yml` mounts `./data` into the container so the SQLite database and the
   local candle cache survive restarts and rebuilds.

3. Check logs / restart / stop:

   ```bash
   docker compose logs -f
   docker compose restart
   docker compose down
   ```

If you don't have a `MASTER_ENCRYPTION_KEY` yet, generate one without installing anything
locally:

```bash
docker compose run --rm bot python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put the result in `.env` before the first `docker compose up`.

## Setup (running without Docker)

1. Create a virtualenv and install the project. The T-Invest SDK (`t-tech-investments`) is
   published on T-Bank's own package index rather than public PyPI, so it needs
   `--extra-index-url`:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]" --extra-index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple
   ```

   (The older PyPI package name `tinkoff-investments` is currently quarantined and won't
   install; `t-tech-investments` from the URL above is the current official SDK, imported in
   code as `t_tech.invest` - same code, renamed after the Tinkoff → T-Bank rebrand.)

2. Copy `.env.example` to `.env` and fill it in:

   ```bash
   cp .env.example .env
   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Put the generated key in `MASTER_ENCRYPTION_KEY`, your bot token (from @BotFather) in
   `TELEGRAM_BOT_TOKEN`, your NewsAPI.org key in `NEWSAPI_KEY`, and a free Gemini API key
   (https://aistudio.google.com/apikey) in `GEMINI_API_KEY`.

   Leave `REAL_TRADING_ALLOWLIST` empty until you've validated a strategy in sandbox mode — it's
   a second gate (besides the in-chat confirmation) that must explicitly list your Telegram user
   ID before `/trade` will place real orders.

3. Get your T-Invest tokens from the Т-Инвестиции app (Настройки → Токены):
   create a **Sandbox** token for demo trading and, only when you're ready, a **production**
   token for real trading. You supply these to the bot with `/start` — they are encrypted with
   `MASTER_ENCRYPTION_KEY` before being stored.

4. Run:

   ```bash
   python -m app.main
   ```

## Security notes

- Never commit `.env` or `data/*.db` — both are already in `.gitignore`.
- An earlier version of this repository had a live Tinkoff token, Telegram bot token, NewsAPI
  key, and Gemini key hardcoded in source files. If you ever pushed that history anywhere, or
  suspect it wasn't fully private, rotate all four credentials from their respective consoles
  before relying on this bot.

## Known issue: T-Invest API TLS certificate

`invest-public-api.tbank.ru` / `sandbox-invest-public-api.tbank.ru` serve a certificate
issued by Russia's Ministry of Digital Development root CA (a consequence of sanctions on
Russian banks), which isn't in any standard OS or language trust store. Without a fix,
every call fails with `self-signed certificate in certificate chain`, regardless of
machine, network, or proxy - this affects any client anywhere, not just this deployment.

The Dockerfile already handles this: it installs the Root/Sub CA certificates from
`gu-st.ru` (Russia's official distribution point for this CA) into the system trust store
and sets `GRPC_DEFAULT_SSL_ROOTS_FILE_PATH` (grpc-python ships its own bundled root
certificates and ignores the OS store otherwise). If you ever run this outside Docker,
you'll need to redo both steps - see the `RUN`/`ENV` block near the top of the Dockerfile.

## Project layout

See `app/` for the package: `db/` (models + encryption), `broker/` (T-Invest client, instruments,
candles), `strategies/` (signal generation, shared by backtest and live), `risk/` (position
sizing and guardrails), `backtest/` (replay engine + reporting), `execution/` (live/demo trading
loop), `news/` (sentiment fetch + cache), `bot/` (Telegram handlers).
