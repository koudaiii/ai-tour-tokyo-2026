# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **private-isu**, a practice environment for ISUCON (Japanese web performance competition). It's a social media-like web application (Python implementation only) designed for learning web performance optimization.

This repository is a fork of [catatsuy/private-isu](https://github.com/catatsuy/private-isu) with the following changes:
- Simplified to Python implementation only (Flask + gunicorn)
- Migrated from MySQL to **PostgreSQL 17**
- Application and configuration files placed at repository root (not under `webapp/`)

## Essential Setup Commands

Before working, initialize the project:
```bash
make init  # Downloads PostgreSQL dump and benchmarker image fixtures
```

### Data Preparation for PostgreSQL

`make init` downloads and decompresses a PostgreSQL custom-format dump (`sql/isuconp_data.dump`):
```bash
make init
```

Docker Compose initializes PostgreSQL via `/docker-entrypoint-initdb.d` using:
- `script/restore` (restores `sql/isuconp_data.dump` with `pg_restore`)

Note: bootstrap SQL helpers under `sql/bootstrap_*.sql` are fixed to `isuconp` role/database for local auto-fix checks.

## Common Development Commands

### Building Applications

**Benchmarker:**
```bash
cd benchmarker
make  # builds to ./bin/benchmarker
```

### Running Applications

**Docker Compose (recommended for development):**
```bash
docker compose up
```

Services: nginx (port 80), app (gunicorn on port 8080), postgres (port 5432), memcached.

The postgres service has a healthcheck (`pg_isready`), and the app waits for it before starting.

**Running benchmarker:**
```bash
cd benchmarker
./bin/benchmarker -t "http://localhost:8080" -u ./userdata
```

**Expected output format:**
```json
{"pass":true,"score":1710,"success":1434,"fail":0,"messages":[]}
```

## Architecture Overview

### Application Structure
- **Runtime**: Python 3.14, Flask, gunicorn
- **Database**: PostgreSQL 17 with users, posts, comments tables
- **DB Driver**: psycopg2-binary with RealDictCursor
- **Cache**: Memcached for session storage (Flask-Session)
- **Web Server**: Nginx 1.28 as reverse proxy
- **Images**: Stored as bytea in database (performance optimization target)

### Key Performance Bottlenecks
The application is intentionally designed with performance issues:
- Images stored in database as bytea BLOBs
- N+1 query problems in timeline generation
- No database indexing optimization
- No connection pooling

### Database Schema
Main tables (PostgreSQL, defined in `sql/bootstrap_create_table.sql`):
- `users`: id (SERIAL), account_name, passhash, authority, del_flg, created_at
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
├── script/
│   ├── restore   # Restore script for PostgreSQL dump
│   ├── bootstrap         # Local environment bootstrap
│   ├── server            # Local web app launcher
│   ├── backup            # DB dump backup helper
│   └── upload-to-github  # Release upload helper
├── templates/            # Jinja2 HTML templates
├── public/               # Static assets (CSS, JS, images)
├── etc/nginx/conf.d/     # Nginx configuration
├── benchmarker/          # Go-based load testing tool
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

## Environment Variables

Key environment variables for the application:
- `ISUCONP_DB_HOST`: Database hostname (default: `localhost`)
- `ISUCONP_DB_PORT`: Database port (default: `5432`)
- `ISUCONP_DB_USER`: Database user (default: `isuconp`)
- `ISUCONP_DB_PASSWORD`: Database password (default: `isuconp`)
- `ISUCONP_DB_NAME`: Database name (default: `isuconp`)
- `ISUCONP_MEMCACHED_ADDRESS`: Memcached server address (default: `localhost:11211`)
