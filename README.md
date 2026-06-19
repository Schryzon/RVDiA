<div align="center">
  <img src="website/static/images/banner.png" alt="RVDiA's Banner" width="65%" height="65%">
</div>

<p align="center">
  <a href="https://discord.com/api/oauth2/authorize?client_id=957471338577166417&permissions=1514446056561&scope=bot%20applications.commands">
    <img src="https://img.shields.io/badge/SCHRYZON-RVDIA-ff4df0?style=for-the-badge&logo=python&logoColor=yellow" alt="SCHRYZON - RVDiA">
  </a>
  <a href="https://discord.gg/QqWCnk6zxw">
    <img alt="Discord" src="https://img.shields.io/discord/877009215271604275?style=for-the-badge&logo=discord&logoColor=white">
  </a>
  <a href="https://github.com/sponsors/Schryzon">
    <img alt="Sponsor" src="https://img.shields.io/badge/Sponsor-RVDIA-ea4aaa?style=for-the-badge&logo=github-sponsors&logoColor=white">
  </a>
  <a href="https://saweria.co/Schryzon">
    <img alt="Saweria" src="https://img.shields.io/badge/Saweria-Support-faae2b?style=for-the-badge&logo=ko-fi&logoColor=white">
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?style=flat-square&logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/License-AGPL--3.0-orange?style=flat-square" alt="License: AGPL-3.0">
  <img src="https://img.shields.io/badge/Deployed%20with-Railway-black?style=flat-square&logo=railway" alt="Deployed with Railway">
  <img src="https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square" alt="Status: Active">
</p>

<p align ="center">
  <a href="https://top.gg/bot/957471338577166417">
    <img src="https://top.gg/api/widget/957471338577166417.svg">
  </a>
</p>

---

# 🤖 RVDiA (Revolusioner, Virtual, Independen)

**Revolutionary Virtual Discord Assistant (RVDiA)** is a high-performance, Indonesian-oriented Discord entertainment companion and utility bot built entirely on a modern Python stack. It features deep AI-driven personality integration, an advanced local GPU rendering pipeline, professional-grade image processing, a turn-based RPG battle engine, and a premium **web dashboard** that allows real-time configuration, player interactions, and widget embeddings.

---

## Table of Contents
1. [Core Features](#core-features)
2. [Database Schema & Architecture](#database-schema--architecture)
3. [Local GPU Generation Pipeline](#local-gpu-generation-pipeline)
4. [Web Dashboard & REST APIs](#web-dashboard--rest-apis)
5. [Embeddable Web Chat Widget](#embeddable-web-chat-widget)
6. [Local Development Setup](#local-development-setup)
7. [Deployment](#deployment)
8. [Credits & Contributors](#credits--contributors)

---

## Core Features

### Turn-Based RPG Battle Engine
* **Tactical In-Battle Interface**: Features paginated Select Menus (complying with Discord's API limits) for skills and equipments, complete with real-time health trackers and active state monitoring.
* **Shop & Inventory**: Over **100+ items, skills, and equipments** configured in JSON and dynamically translated based on locale settings.
* **Boss Fights & Elite Tiers**: Challenging bosses with complex phases (e.g., Demi-fiend, Nahobino) and unique mechanisms.

### Advanced Image Processing Toolkit
* **Mathematical Comparison**: Employs OpenCV and Matplotlib to analyze and graph visual histograms side-by-side. Supports multiple metric engines (`correl`, `chisqr`, `intersect`, `bhattacharyya`).
* **Paginated Navigation**: Built-in interactive Discord UI button components enabling fast Next/Prev searching for internet images directly inside message threads.

### Persistent AI Memories
* **Contextual Recall**: Integrates Google Gemini API with [Prisma Client Python](https://prisma-client-py.readthedocs.io/) and vector embeddings to search, record, and write persistent user interactions.
* **Linguistic Title Casing**: Intelligent formatter processing title-casing rules tailored specifically for Indonesian and English grammatical structures.

---

## Database Schema & Architecture

RVDiA relies on PostgreSQL for persistence, mapped via [schema.prisma](file:///c:/Users/nyoma/OneDrive/Desktop/RVDIA/schema.prisma). The core models are organized as follows:

```mermaid
erDiagram
    User ||--o| Inventory : "owns"
    User ||--o| Guild : "member of"
    User ||--o| UserSettings : "customizes"
    User ||--o{ Message : "sends"
    User ||--o{ Memory : "associates"

    User {
        BigInt id PK
        Int hp
        Int max_hp
        Json data "Level, EXP, Coins, Karma, Stats"
        DateTime premiumUntil
    }

    Guild {
        Int id PK
        String name
        String tagline
        String iconUrl
        BigInt ownerId
    }

    Inventory {
        Int id PK
        BigInt userId FK
        Json items "IDs & quantities"
        Json skills "learned skills"
        Json equipments "equipped items"
    }

    UserSettings {
        BigInt userId PK
        String lang "en/id"
    }
```

* **Relations Cascading**: Disbanding a guild safely disconnects all user relations in the database. Deleting users cleanly cascade-deletes their related `Inventory` record.

---

## Local GPU Generation Pipeline

To perform heavy Stable Diffusion inference (`Meina/MeinaMix_V11`) without exhausting memory on a low-VRAM development machine (RTX 3050 4GB), RVDiA offloads rendering to a localized laptop server. The process is gated by interactive Windows notification checks to prevent background disruptions:

```mermaid
sequenceDiagram
    actor User as Discord User
    participant Bot as RVDiA Bot (Railway)
    participant Server as GPU Server (Local Laptop)
    actor Owner as Laptop Owner (Schryzon)

    User->>Bot: Slash Command /generate [prompt]
    Bot->>Server: GET /ping (X-API-Key)
    alt Server Offline
        Bot-->>User: Reply: "Artist Offline"
    else Server Online
        Bot->>Server: POST /generate [prompt, username, is_nsfw]
        Note over Server: Check NSFW blacklist (if SFW channel)
        alt NSFW Blocked
            Server-->>Bot: 400 Bad Request (NSFW Blocked)
            Bot-->>User: Reply: "NSFW content blocked!"
        else Allowed
            Server-->>Bot: 200 OK (request_id)
            Bot->>User: Defer response (loading...)
            Server->>Owner: Winotify / Tkinter gated approval prompt
            alt Owner Declines
                Owner->>Server: Click "Decline"
                Server->>Server: Update status: declined
            else Owner Approves
                Owner->>Server: Click "Approve"
                Server->>Server: Update status: generating
                Note over Server: Load SD model & Move CPU -> CUDA GPU
                Server->>Server: Generate Image (512x512 PNG)
                Note over Server: Move CUDA -> CPU & Aggressive VRAM Clear
                Server->>Server: Save image & Update status: completed
            end
            loop Poll Status (Every 2s, max 15m)
                Bot->>Server: GET /status/[request_id]
                Server-->>Bot: Status (pending/generating/declined/completed)
            end
            alt Status: Completed
                Bot->>Server: GET /image/[request_id]
                Server-->>Bot: Image File
                Bot-->>User: Send generated image!
            else Status: Declined
                Bot-->>User: Reply: "Generation declined by artist."
            else Status: Failed / Timeout
                Bot-->>User: Reply: "Generation failed."
            end
        end
    end
```

---

## Web Dashboard & REST APIs

The web interface is hosted on `aiohttp` and `Jinja2` with zero Node dependencies, utilizing standard CSS and clean Javascript logic.

### Authentication
Authentication utilizes a secure Discord OAuth2 authorization flow. Sessions are persisted client-side using HMAC-signed cookies to prevent hijacking.

### Endpoints Definition (in [routes.py](file:///c:/Users/nyoma/OneDrive/Desktop/RVDIA/scripts/api/routes.py))

| Method | Endpoint | Description | Auth Required |
| :--- | :--- | :--- | :---: |
| **GET** | `/api/v1/user/profile` | Fetches authenticated user's profile metadata and currencies. | Yes |
| **GET** | `/api/v1/user/inventory` | Fetches the user's item, skill, and equipment logs. | Yes |
| **GET** | `/api/v1/stats` | System metrics (uptime, CPU/RAM, command executions). | No |
| **POST** | `/api/v1/chat` | Send a prompt to the context-aware chat engine. | Yes |
| **GET** | `/api/v1/shop` | Fetches the translated list of marketplace items, categorized. | Yes |
| **POST** | `/api/v1/shop/buy` | Purchase a shop item (consumable, skill, equipment). | Yes |
| **GET** | `/api/v1/leaderboard` | Fetches Top Players or Guilds ranked rankings. | Yes |
| **GET** | `/api/v1/guild` | Fetches active guild stats, tagline, icon, and member list. | Yes |
| **POST** | `/api/v1/guild/create`| Spawns a guild for 5,000 Coins. | Yes |
| **POST** | `/api/v1/guild/edit` | Modifies the guild name, tagline, or icon URL. | Yes |
| **POST** | `/api/v1/guild/kick` | Kicks a member (only available to the guild owner). | Yes |
| **POST** | `/api/v1/guild/leave` | Leave/disband the guild. | Yes |
| **POST** | `/api/v1/public/chat` | Session-hashed public endpoint for the web widget. | No |

---

## Embeddable Web Chat Widget

RVDiA features an embeddable chat script allowing users to interface with the AI assistant from external web pages.

### Security & Session-Hashing
To avoid polluting the database with arbitrary guest entries, the public endpoint `/api/v1/public/chat` handles stateless traffic by mapping incoming client UUIDs:
1. Client generates a random UUID on their first load and saves it to `localStorage`.
2. The server hashes this string using **SHA-256** and extracts the first 8 bytes.
3. This creates a positive 63-bit signed integer representation which serves as a virtual Discord user ID context in PostgreSQL.
4. Allows persistent, isolated chat threads per web visitor without requiring Discord login credentials.

### Quickstart Embed
Include this script tag inside your HTML body to launch the chatbot:
```html
<script 
  src="http://localhost:8080/static/js/rvdia-widget.js"
  data-api-url="http://localhost:8080" 
  data-lang="id"
  defer>
</script>
```

### Developer Testbed
Creators can visit the built-in development sandbox at `/widget-demo` to inspect the embedded script, configure language settings, and view real-time API logs detailing requests, UUID-to-ID hashes, and response packages.

---

## Local Development Setup

Follow these steps to set up and run RVDiA on a Windows machine.

### Prerequisites
* **PowerShell 5.1+** (or modern PowerShell Core)
* **Python 3.12** (Scoop package manager is recommended: `scoop install python312`)
* **PostgreSQL** database instance.

### Step-by-Step Installation
1. **Clone the repository**:
   ```powershell
   git clone https://github.com/Schryzon/RVDiA.git
   cd RVDiA
   ```

2. **Configure Environment Variables**:
   Copy `.env.example` to `.env` and fill out your api credentials, discord developer credentials, and local postgres database link:
   ```powershell
   copy .env.example .env
   ```

3. **Install Requirements**:
   ```powershell
   pip install -r requirements.txt
   ```

4. **Initialize Prisma Client**:
   Generate database abstractions and sync models:
   ```powershell
   # Generate schema bindings
   prisma generate
   
   # Synchronize models to Postgres
   prisma db push --accept-data-loss
   ```

5. **Launch the Engine**:
   Run the main bot and web panel:
   ```powershell
   python RVDIA.py
   ```
   The dashboard will be active at `http://localhost:8080`.

---

## Deployment

RVDiA is configured for seamless deployment on **Railway** using the provided [Dockerfile](file:///c:/Users/nyoma/OneDrive/Desktop/RVDIA/Dockerfile) and [railway.toml](file:///c:/Users/nyoma/OneDrive/Desktop/RVDIA/railway.toml).

When launching in a production container, [start.sh](file:///c:/Users/nyoma/OneDrive/Desktop/RVDIA/start.sh) runs automatically, ensuring the prisma database models are pushed and client headers are rebuilt before spawning `RVDIA.py`.

---

## Credits & Contributors

### Special Acknowledgments
* **Concept Inspiration**: Riverdia.
* **Advisors & Core Testers**: iMaze, Mouchi, Dez, Zenchew, Ismita, Pockii, Kyuu, Kazama, Bcntt, Nateflakes, nathawiguna, opensourze, Shiruto, Satya Yoga.

---

**Made with ❤️ and dedication by Jayananda and contributors.**

*Rebirth: 30/04/2026*