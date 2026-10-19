# LoL Personal Stats Tracker

A local League of Legends dashboard integrating Riot Games APIs, with a Python backend, SQLite caching and a vanilla JavaScript frontend.

## Features

- Account overview, ranked statistics and rank history.
- Match history and match details, including gold timelines and performance summaries.
- Champion mastery, teammate statistics, activity and live-game information.
- Local SQLite caching and retry handling for API rate limits.

## Requirements

- Python 3.10 or newer. The backend uses only the standard library; no pip installation is needed.
- Your own valid Riot Games API key and the Riot IDs you want to inspect.
- Internet access to Riot APIs, Data Dragon and the Chart.js CDN.

## Run locally

```sh
git clone https://github.com/rubensauriosD/lol-stats.git
cd lol-stats
cp .env.example .env
cp accounts.example.json accounts.json
```

Set `RIOT_API_KEY` in `.env` and replace the example account in `accounts.json`. Keep both local files private. Development keys expire; renew yours through the [Riot Developer Portal](https://developer.riotgames.com/) when necessary.

The account fields are `label`, `gameName`, `tagLine` and `platform`. Examples of platform codes include `la2`, `br1`, `na1` and `euw1`; `backend/config.py` lists the supported routes. The backend infers the regional routing cluster.

```sh
cd backend
python3 main.py
```

Open `http://localhost:8000`. Leave the terminal running; `Ctrl+C` stops the server. A fresh SQLite cache is created automatically in `data/`.

## Structure

```text
backend/main.py          Local HTTP server and dashboard endpoints
backend/riot_client.py   Riot API client, timeouts and rate-limit retries
backend/cache.py         SQLite persistence
backend/stats.py         Statistics and match summaries
backend/insights.py      Match analysis
backend/config.py        Local configuration and platform routing
static/                  Browser dashboard
```

## Private configuration

The API key stays on the backend. `.env`, `accounts.json`, cached matches, player identifiers and local databases are excluded from Git. Only placeholder configuration is included here; no real account data or API responses are published.

Designed for local, single-user use. This is an independent personal project, not an official Riot Games product. League of Legends and related assets belong to Riot Games.

Built by [Ruben Bazan](https://github.com/rubensauriosD).
