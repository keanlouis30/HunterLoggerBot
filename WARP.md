# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

HunterLoggerBot is a Discord bot that tracks user login/logout activities and logs them to Google Sheets. The bot integrates with Google Sheets API for data persistence and includes a Flask web server for deployment on platforms like Render.

### Architecture

The application follows a single-module architecture with the following key components:

1. **Discord Bot Client**: Handles Discord events and messages using discord.py
2. **Google Sheets Integration**: Uses gspread for reading/writing to Google Sheets with service account authentication
3. **Timezone Management**: All timestamps are localized to Asia/Manila timezone
4. **Asynchronous Operations**: Uses async/await pattern for non-blocking Google Sheets operations

### Key Data Flow

- Users send `@login` or `@logout` commands in Discord channels
- Bot processes commands asynchronously and writes to separate "Log In" and "Log Out" sheets
- Data is organized by date with color coding (green for login, red for <8hrs logout, blue for ≥8hrs logout)
- Monthly statistics are generated on-demand and written to a "Statistics" sheet

## Common Commands

### Development Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment variables (create .env file)
# Required: DISCORD_BOT_TOKEN
# Optional: WORKBOOK_NAME (defaults to "Hunter_Logging")

# Run the bot locally
python logging_bot.py
```

### Testing
```bash
# Test Google Sheets connection
python -c "import gspread; from oauth2client.service_account import ServiceAccountCredentials; print('Imports successful')"

# Test Discord bot token (will fail but validate token format)
python -c "import discord; import os; from dotenv import load_dotenv; load_dotenv(); print('Token loaded:', bool(os.getenv('DISCORD_BOT_TOKEN')))"
```

### Deployment
The bot is configured for cloud deployment with:
- Support for both local (`credentials.json`) and production (`/etc/secrets/credentials.json`) credential paths
- Environment variable configuration
- UptimeRobot used for monitoring and keeping the bot alive

## Authentication Setup

### Google Sheets API
1. Create a Google Cloud project and enable Sheets API
2. Create a service account and download credentials as `credentials.json`
3. Share the target Google Sheet with the service account email
4. Required sheets: "Log In", "Log Out", "Statistics" (auto-created)

### Discord Bot
1. Create application in Discord Developer Portal
2. Create bot user and copy token to `DISCORD_BOT_TOKEN` environment variable
3. Enable required intents: messages, guilds, members, message_content

## Code Structure Guidelines

### Async Pattern
All Google Sheets operations use the `run_blocking` helper to convert synchronous gspread calls to async:
```python
result = await run_blocking(sheet.get_all_values)
```

### Sheet Data Organization
- Date headers are formatted as "Month Day, Year" (e.g., "October 13, 2025")
- Each date section has: Date header → Column headers (Time, Name, Role) → Data rows
- Data parsing assumes this specific structure

### Color Coding System
- Green: Login events
- Red: Logout after less than 8 hours
- Blue: Logout after 8+ hours
- Applied using gspread_formatting CellFormat

### Error Handling
Critical errors (missing token, failed Google Sheets connection) cause the bot to exit. Non-critical errors are logged but don't stop execution.

## Environment Variables

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `DISCORD_BOT_TOKEN` | Yes | Discord bot authentication token | None |
| `WORKBOOK_NAME` | No | Google Sheets workbook name | "Hunter_Logging" |

## Bot Commands

- `@login` - Records user login with timestamp and roles
- `@logout` - Records user logout with duration-based color coding
- `@statistics` - Generates monthly statistics report in Google Sheets

## Key Dependencies

- `discord.py` - Discord API wrapper
- `gspread` + `gspread-formatting` - Google Sheets API client
- `oauth2client` - Google API authentication
- `pytz` - Timezone handling for Manila timezone
- `python-dotenv` - Environment variable loading
