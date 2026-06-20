# 🧠 RVDiA Developer Guide & LLM Coding Skill

Welcome! If you are an AI assistant or human developer modifying the **RVDiA (Revolutionary Virtual Digital Assistant)** repository, you must read and adhere to this guide. It ensures that the system architecture, Jay's system-designer coding style, database relationships, and localization flows remain clean, predictable, and correct.

---

## ✦ 1. Project Vision & Architecture

RVDiA is an interactive, global-friendly digital companion combining conversational AI, a modular text-based RPG (`Re:Volution ~ The Dream World`), advanced image processing filters, and server utilities.

### System Entry Points & Bootstrapping (`RVDIA.py`)
* **Bot Client**: `RVDIA` is a subclass of `commands.AutoShardedBot`.
* **Prisma Connection**: The database is connected during the `setup_hook` event loop initialization.
* **Parallel Adapters**: The bot launches a local REST API web server (`scripts/api/web_server.py`) and a Telegram Bot polling adapter (`scripts/telegram_bot.py`) concurrently within its event loop.
* **Cog Loading**: Cogs inside `/cogs` are loaded dynamically using `pkgutil.iter_modules()` in `on_ready`.
* **Dynamic Replies**: Direct message replies referencing an RVDiA chatbot response automatically trigger `send_reply_message()` using Google GenAI, preserving thread context.
* **Admin Transfer System**: Account data transfers between Discord accounts are triggered by direct replies (`approve`/`accept` or `decline`/`deny`) to transfer embeds, which merge Level/EXP JSON data and inventory items/skills database records.

---

## ✦ 2. Prisma Database Schema

We use PostgreSQL with Prisma client mapping. Here are the core models defined in `schema.prisma`:

* **`User`**: Core RPG player stats. Contains `id` (Discord User ID as BigInt), `hp`, `max_hp`, `data` (Json representing Level, EXP, Coins, Karma, Stats), `guildId`, and `premiumUntil`.
* **`Guild`**: RPG guild system. Tracks guild `id`, `name`, `tagline`, `ownerId` (BigInt), and links to a list of `members` (`User[]`).
* **`Inventory`**: Stores `userId` (foreign key linked to `User`), `items` (Json quantity map), `skills` (Json mapping of learned skills), and `equipments` (Json equipped slots).
* **`Warning`**: Tracks server warning points. Contains warning `id`, `guildId` (BigInt), `userId` (BigInt), and `reason` (String).
* **`Blacklist`**: Restricts specific users from invoking commands. Contains `id` (BigInt) and `reason`.
* **`Memory`**: Vector storage for chat memories. Contains `userId`, `content`, `embedding` (384-dimensional vector for cosine similarity semantic searches), and `isPersistent` (whether to keep it permanently or let it expire).
* **`UserSettings`**: Personalization options. Stores `userId` (BigInt) and `lang` (String, defaults to "en").

---

## ✦ 3. Jay's System Design Guidelines (Code Style)

All code modifications must match the following guidelines:

1. **Readability & Control**
   Keep spacing clean and format consistently. Visual noise must be kept to a minimum.
2. **Naming Conventions**
   * Use **`snake_case`** for all function names, variables, parameters, and filenames (e.g. `user_settings`, `img_rgb`, `process_and_reply`).
   * Never use flashes like camelCase or rigid PascalCase for system logic.
3. **Flat Logic (Anti-Deep Nesting)**
   Avoid deep indentations. Lean towards early returns and guard clauses.
   ```python
   # Correct (Early Return):
   if not user:
       return await ctx.reply("User not found!")
   # Proceed with logic
   ```
4. **Optimistic Error Handling (Let it Crash)**
   If a command encounters an error, do not swallow it. Let it crash or print the full stack trace so bugs can be resolved immediately. In `RVDIA.py`, errors are captured and piped to the developer's Discord channel via `format_error_report()`.
5. **Smart Title Casing**
   Use `scripts.main.smart_title_case(text)` to automatically capitalize headers while keeping prepositions/conjunctions in lowercase (Indonesian and English supported) and preserving the case of the name "RVDiA".
6. **Sentence-Boundary Truncation**
   Use `scripts.main.clean_truncate(text, max_char)` to truncate long AI outputs cleanly at complete sentence boundaries (matching periods, exclamation marks, or question marks) to avoid incomplete thoughts.

---

## ✦ 4. How to Register Commands

Commands must be defined inside `/cogs/` as hybrid commands so they sync as both prefix text and Discord Slash commands.

### Decorator Standards:
* **English Default**: Register names, descriptions, parameter names, and parameter descriptions directly in decorators using **English only**.
  ```python
  @commands.hybrid_command(
      name="weather",
      aliases=['cuaca'],
      description="Check the weather in a city or area!"
  )
  @app_commands.describe(location="City or area to search weather for")
  @check_blacklist()
  async def weather(self, ctx: commands.Context, *, location: str):
      """Check the weather in a city or area!"""
      # Logic...
  ```
* **Guard Checks**: Use shared decorators from `scripts.main` to enforce business logic:
  * `@check_blacklist()`: Prevents blacklisted users from running the command.
  * `@has_registered()`: Validates that the user has initialized their Re:Volution RPG profile.
  * `@is_premium()`: Restricts commands to players with an active premium status check.
  * `@has_pfp()`: Requires the user to have a Discord avatar.
  * `@event_available()`: Restricts command execution to active server event phases.

---

## ✦ 5. Dynamic Bilingual Help Menus & Locale Mapping

While commands register globally on Discord's UI in English, the interactive help menus (`scripts/help_menu/help.py`) translate names, descriptions, and parameters dynamically at runtime based on the user's language settings.

### Dynamic Resolution Mechanism:
When generating pages, the help command resolves keys using dotted key paths pointing to the locales:
* **Category Titles**: `help.category_<cog_key>`
* **Category Descriptions**: `help.category_<cog_key>_description`
* **Command Descriptions**: `commands.<qualified_name>.description` (subcommands resolve as `commands.<parent>.<child>.description`)
* **Parameter Hints**: `commands.<qualified_name>.arguments.<parameter_name>`

### Adding Translations:
Whenever you create or modify a command, you **MUST** update both [locales/en.json](locales/en.json) and [locales/id.json](locales/id.json) under the `"commands"` root key:

```json
"commands": {
    "my_command": {
        "description": "Tampilkan informasi bantuan." or "Show help details.",
        "arguments": {
            "parameter_name": "Parameter deskripsi bahasa." or "Parameter description details."
        }
    }
}
```

This dynamic approach keeps Discord slash command syncing fast and clean in English, while providing a fully localized, rich help menu experience matching the user's language settings!


---

## ✦ 6. Discord Native AutoMod Guidelines

RVDiA supports server moderation using **Discord's Native AutoMod API**. This allows administrators to manage safety filters programmatically.

### Core Architecture:
* **Gateway Intent-Free**: Native AutoMod rules run directly on Discord's servers. RVDiA manages them via REST API calls (e.g. `Guild.create_automod_rule`), avoiding the need for the privileged gateway `Message Content Intent`.
* **Required Permissions**: 
  * The bot must have the **Manage Server** (`manage_guild`) permission to view, edit, or delete rules. This permission is included by default in the bot's standard invite link permissions bitmask (`1514446056561`).
  * Command decorators must enforce `@commands.has_permissions(manage_guild=True)` and `@commands.bot_has_permissions(manage_guild=True)` to prevent unauthorized rule tampering.

---

Glub glub, wiggle wiggle! 🐟😺 Keep the machinery running smoothly!
