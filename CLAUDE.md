# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **private-isu**, a practice environment for ISUCON (Japanese web performance competition). It's a social media-like web application (Python implementation only) designed for learning web performance optimization.

This repository is a fork of [catatsuy/private-isu](https://github.com/catatsuy/private-isu) with the following changes:
- Simplified to Python implementation only (Flask + gunicorn)
- Migrated from MySQL to **PostgreSQL 18**
- Application and configuration files placed at repository root (not under `webapp/`)

## Essential Setup Commands

Before working, initialize the project:
```bash
script/bootstrap
```

## Common Development Commands

### Building Applications


### Running Applications

**Docker Compose (recommended for development):**
```bash
docker compose up
```

Services: nginx (port 80), app (gunicorn on port 8080), postgres (port 5432), memcached.

The postgres service has a healthcheck (`pg_isready`), and the app waits for it before starting.


## Architecture Overview

### Application Structure
- **Runtime**: Python 3.14, Flask, gunicorn
- **Database**: PostgreSQL 18 with users, posts, comments tables
- **DB Driver**: psycopg2-binary with RealDictCursor
- **Cache**: Memcached for session storage (Flask-Session)
- **Web Server**: Nginx 1.28 as reverse proxy
- **API Gateway**: Azure API Management (Consumption SKU, OpenAPI spec from `openapi.yaml`)
- **Images**: Stored as bytea in database (performance optimization target)

### Key Performance Bottlenecks
The application is intentionally designed with performance issues:
- Images stored in database as bytea BLOBs
- N+1 query problems in timeline generation
- No database indexing optimization
- No connection pooling

### Database Schema
Main tables (PostgreSQL, defined in `sql/bootstrap_create_table.sql`):
- `users`: id (SERIAL), account_id, passhash, authority, del_flg, created_at
- `posts`: id (SERIAL), user_id, mime, imgdata (bytea), body, created_at
- `comments`: id (SERIAL), post_id, user_id, comment, created_at

### Core Application Features
- User registration and authentication
- Image upload and display
- Timeline feed with posts and comments
- User profile pages
- Admin ban functionality

## File Structure
```
├── app.py                # Main Flask application
├── pyproject.toml        # Python dependencies (uv)
├── Dockerfile            # Python app container (python:3.14-slim)
├── compose.yml           # Docker Compose (nginx, app, postgres, memcached)
├── sql/
│   ├── bootstrap_create_table.sql      # PostgreSQL table definitions
│   ├── bootstrap_*.sql   # SQL helpers used by script/bootstrap checks/fixes
│   ├── isuconp_data.dump # PostgreSQL custom-format dump (from make init, ignored)
│   └── .gitignore        # Ignores *.bz2 and *.dump
├── mcp-server/
│   ├── function_app.py   # Azure Functions MCP server (scenario-based tools)
│   ├── requirements.txt  # Python dependencies (azure-functions>=1.24.0)
│   ├── host.json         # Functions host config with extension bundle
│   └── local.settings.json # Local dev settings (gitignored)
├── script/
│   ├── bootstrap         # Local environment bootstrap
│   ├── server            # Local web app launcher
│   ├── azurite           # Start Azurite local storage emulator
│   ├── mcp-server        # Start MCP server locally
│   ├── deploy-infra      # Deploy Azure infra from infra/main.bicep
│   ├── deploy-func       # Deploy MCP server code to Azure Functions
│   ├── restore           # Restore script for PostgreSQL dump
│   ├── backup            # DB dump backup helper
│   └── upload-to-github  # Release upload helper
├── infra/                # Bicep templates for Azure infrastructure
├── templates/            # Jinja2 HTML templates
├── public/               # Static assets (CSS, JS, images)
├── etc/nginx/conf.d/     # Nginx configuration
├── provisioning/         # Ansible playbooks
└── manual.md             # Competition manual
```

## Performance Optimization Guidelines

Common optimization targets:
1. Move image storage from database (bytea) to filesystem
2. Add database indexes for timeline queries
3. Implement proper caching strategies
4. Optimize N+1 queries with JOIN operations
5. Use CDN for static assets
6. Implement connection pooling

## Python Implementation Details
- Framework: Flask with gunicorn WSGI server
- Dependencies managed via `uv` (pyproject.toml / uv.lock)
- Memcached integration via `pymemcache` (Flask-Session)
- PostgreSQL via `psycopg2-binary` with `RealDictCursor`
- Templates: Jinja2 (in `templates/`)

## Remote MCP Server

The `mcp-server/` directory contains an Azure Functions app that exposes MCP tools for the private-isu API.

### Architecture
- **Runtime**: Azure Functions Python v2 programming model
- **Transport**: Streamable HTTP (endpoint: `/runtime/webhooks/mcp`)
- **Backend**: Tools call the private-isu API (`API_BASE_URL`)
- **Storage**: Azure Queue Storage required by MCP extension (Azurite locally)

### MCP Tools
- `browse_timeline` - Browse posts with keyword filter and pagination
- `explore_user` - User profile + stats + recent posts in one call
- `find_popular_posts` - Posts ranked by engagement (comment count)
- `get_conversation` - Post + comment thread in readable format
- `compare_users` - Side-by-side user activity comparison
- `search_posts` - Keyword search across posts and comments

### Local Development
Requires three processes running simultaneously:
```bash
script/server      # API server (port 8080)
script/azurite     # Azurite storage emulator (ports 10000-10002)
script/mcp-server  # MCP server (port 7071)
```

### Deployment
```bash
script/deploy-infra  # Deploy Azure infrastructure (first time)
script/deploy-func   # Deploy MCP server code (repeatable)
```

## Environment Variables

Key environment variables for the application:
- `ISUCONP_DB_HOST`: Database hostname (default: `localhost`)
- `ISUCONP_DB_PORT`: Database port (default: `5432`)
- `ISUCONP_DB_USER`: Database user (default: `isuconp`)
- `ISUCONP_DB_PASSWORD`: Database password (default: `isuconp`)
- `ISUCONP_DB_NAME`: Database name (default: `isuconp`)
- `ISUCONP_MEMCACHED_ADDRESS`: Memcached server address (default: `localhost:11211`)
- `APIM_NAME`: Azure API Management instance name (set by `script/deploy-infra`)
- `APIM_GATEWAY_URL`: API Management gateway URL (set by `script/deploy-infra`)
- `FUNCTION_APP_NAME`: Azure Functions app name (set by `script/deploy-infra`)
- `FUNCTION_APP_MCP_ENDPOINT`: Remote MCP endpoint URL (set by `script/deploy-infra`)
