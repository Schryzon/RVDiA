<div align="center">
  <img src="https://repository-images.githubusercontent.com/610636239/51177a45-e951-42e4-bb6d-128c0bb39d5f" alt="RVDiA's Banner" width="65%" height="65%">
</div>

<p align="center">
  <a href="https://discord.com/api/oauth2/authorize?client_id=957471338577166417&permissions=1514446056561&scope=bot%20applications.commands">
    <img src="https://img.shields.io/badge/SCHRYZON-RVDIA-ff4df0?style=for-the-badge&logo=python&logoColor=yellow" alt="SCHRYZON - RVDiA">
  </a>
  <a href="https://discord.gg/QqWCnk6zxw">
    <img alt="Discord" src="https://img.shields.io/discord/877009215271604275?style=for-the-badge&logo=discord&logoColor=white">
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

# RVDiA
## "Revolusioner, Virtual, Independen."
Revolutionary Virtual Discord Assistant (RVDiA) is an **Indonesian-oriented Fun Bot focused on Games and Image Processing**.

## What's Special About This Bot?
This bot is in Indonesian and has special commands for members of the G-Tech Re'sman club. It also offers a variety of utilities, its own RPG (role-playing game) system, and a **dynamic web dashboard**.

## Core Features & Recent Updates
- **RPG Battle System**: A deep, turn-based combat system with levels, stats, and skills.
    - **Massive Content**: Over **100+ items and skills** available in the paginated Shop.
    - **Elite Challenges**: New **FINAL BOSS** tier featuring multi-phase threats like Demi-fiend and Nahobino.
    - **Persona Integration**: Added legendary protagonists Makoto Yuki, Yu Narukami, and Ren Amamiya as high-stakes Bonus Enemies.
    - **Tactical UI**: Enhanced in-battle UI with real-time stat checking and detailed enemy skill analysis.
- **Local AI Architecture**: Decoupled from proprietary cloud services for enhanced privacy and cost-efficiency.
    - **Multilingual Search**: Optimized for English and Indonesian casual chat behaviors.
- **Dynamic Web Dashboard**: Built with `aiohttp` and `Jinja2` featuring premium Glassmorphism aesthetics and multilingual support (ID/EN).

## Want to Tinker with It Yourself?
1. Clone this repo or download the latest release from tags;
2. Get a Discord bot token & Top.gg token;
3. Get a PostgreSQL Database URL (`DATABASE_URL`) for Prisma;
4. Get an OpenWeather API key, OpenAI key (for DALL-E), and Google Gemini API key (`googlekey`).
* There might be more necessities.

(For the `.env` format, check out `.env.example`. Remember to keep your bot secure!)

## Additional Information
This project is __just for fun__ and to improve my programming skills regarding virtual bots and web apps.

Currently, RVDiA is configured to be hosted using **Railway via Docker**. So, if you want to run the bot, I recommend using Railway's services. But, if you just want to run the bot locally on your personal computer, that's no problem.

Run `./start.sh` (or deploy via Docker) to start the bot. This script will automatically generate the Prisma client, push the database schema, and run both RVDiA and the Xelvie monitor. The web dashboard will be accessible at `http://localhost:8080` (or the configured `PORT`).

Join the [CyroN Central server](https://discord.gg/QqWCnk6zxw) on Discord and contact me (Schryzon) if you have any issues, questions, or want to collaborate on RVDiA's development.

### Credits
Special thanks to Riverdia (for inspiring the bot's name), iMaze, Mouchi, Dez, Zenchew, Ismita, Pockii, Kyuu, Kazama, Bcntt, Nateflakes, nathawiguna, opensourze, Shiruto, Satya Yoga, and many more for helping me with previous projects!

**Made with ❤️ and dedication, Jayananda**

## Community
- [Contributing Guidelines](CONTRIBUTING.md)
- [Code of Conduct](CODE_OF_CONDUCT.md)

---

Farewell, Yuyuko, Pandora, and Historia. You will be missed.

`Verified: 01/08/2023`

`End of Life: 08/04/2025`

`Rebirth: 30/04/2026`