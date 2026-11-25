# Member Cloud V2

Independent rebuild of the existing Member Cloud application.

## Stack
- Python 3.11
- Pyrogram 2.x
- PostgreSQL via `DATABASE_URL`
- aiohttp health endpoint
- Docker deployment

## Safety rules
- This repository is separate from `mmnihm/-6` and `mmnihm/Cangku`.
- Preserve the original member, catalog, scan, copy, audit, and admin behavior.
- Never clear production tables, catalog rows, scan checkpoints, or audit records as part of deployment.
- Scanner session values are credentials. Do not commit them to GitHub or print them in logs.
- Verify scanner login, PostgreSQL persistence read-back, and reconnect after restart before declaring deployment complete.

## Required environment
`BOT_TOKEN`, `API_ID`, `API_HASH`, `ADMIN_ID`, and PostgreSQL `DATABASE_URL`.
Optional: `DATABASE_PATH`, `LOG_LEVEL`, `PORT` / `WEB_PORT`.

## Run
Build and run the included Dockerfile with a persistent volume mounted at `/app/data` and the required environment variables supplied by the host. PostgreSQL remains authoritative when `DATABASE_URL` is configured.
