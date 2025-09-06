# Overview

This is a Telegram music bot project that provides voice chat streaming capabilities for Telegram groups. The bot allows users to play music, manage queues, and handle playlists through voice chat integration. It's built using modern Python libraries for Telegram bot development and voice streaming functionality.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Core Framework
- **Pyrogram**: Primary Telegram client library for bot interactions and user account management
- **PyTgCalls**: Voice chat streaming library that handles audio/video streaming in Telegram voice chats
- **Telethon**: Secondary Telegram client for specific operations
- **Asyncio**: Asynchronous programming pattern throughout the application

## Bot Architecture
- **Dual Client System**: Uses both bot client and user client (via STRING_SESSION) for comprehensive Telegram API access
- **Plugin-based Structure**: Modular plugin system with commands organized in the `plugins/` directory
- **Event-driven Design**: Handles various Telegram events like messages, callbacks, and voice chat updates

## Data Storage
- **MongoDB**: Primary database for storing user sessions, bot configuration, and persistent data
- **Local Caching**: File-based caching system in `/cache` directory for temporary media files
- **In-memory Storage**: Runtime data structures for managing active streams and queues

## Music Streaming System
- **External API Integration**: Uses custom YouTube API service (`api.nub-coder.tech`) for video information and stream URLs
- **yt-dlp Integration**: YouTube downloader for media extraction with automatic version checking and updates
- **Stream Quality Management**: Supports both audio and video streaming with configurable quality settings

## Media Processing
- **Thumbnail Generation**: Custom thumbnail creation using PIL with gradient backgrounds, text overlays, and image manipulation
- **Font Styling**: Unicode-based text styling system with support for italic, superscript, and strikethrough formatting
- **Image Processing**: Automatic image resizing, border addition, and enhancement features

## Configuration Management
- **Environment-based Configuration**: Primary configuration through environment variables
- **Fallback Configuration**: Default values in `config.py` for development environments
- **Flexible Deployment**: Support for both local development and cloud deployment (Heroku-compatible)

## Authentication & Authorization
- **Owner-based Access Control**: Primary owner defined via `OWNER_ID` environment variable
- **Admin List Management**: File-based admin user ID storage in `admin.txt`
- **Session Management**: Pyrogram session strings for user account authentication

# External Dependencies

## APIs and Services
- **Telegram Bot API**: Core bot functionality via BotFather token
- **Telegram Client API**: User account operations via API_ID/API_HASH from my.telegram.org
- **Custom YouTube API**: Video information and streaming URLs via `api.nub-coder.tech`
- **PyPI Registry**: Automatic yt-dlp version checking and updates

## Database Services
- **MongoDB Atlas**: Cloud MongoDB instance for persistent data storage
- **Connection URI**: Configurable via `MONGODB_URI` environment variable

## Media Processing Libraries
- **PIL (Pillow)**: Image manipulation and thumbnail generation
- **FFmpeg**: Media processing and format conversion
- **pymediainfo**: Media file information extraction

## Deployment Platforms
- **Heroku**: Cloud deployment support with `app.json` configuration
- **Replit**: Development environment compatibility
- **Local Development**: Direct Python execution support

## Required Credentials
- Telegram Bot Token from @BotFather
- Telegram API credentials (API_ID, API_HASH) from my.telegram.org
- Pyrogram session string for user account
- MongoDB connection URI
- Custom API token for YouTube service (NUB_YTDLP_API)

## Optional Integrations
- Logging group for error reporting (LOGGER_ID)
- Support group and channel integration
- Admin notification system