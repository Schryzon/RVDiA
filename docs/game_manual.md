# Re:Volution ~ The Dream World - Game Manual

## Overview
Re:Volution is an RPG (Role-Playing Game) built directly into RVDiA. Players explore, fight enemies, gain EXP/Levels, and collect items/skills.

## Combat & Stats System
- **HP (Health Points)**: When this reaches 0, the player/enemy is defeated.
- **Attack (ATK)**: Determines base damage. Damage formula heavily relies on ATK and the enemy's DEF. Minimum damage is 5% of ATK.
- **Defense (DEF)**: Reduces incoming damage. The formula is `(ATK * (120 / (120 + DEF)))`. Defending during combat boosts DEF temporarily by 8-15 points.
- **Agility (AGL)**: Determines turn order and Dodge/Miss chance. Higher AGL than the opponent increases the chance to dodge their attacks (Max 40% dodge chance from AGL).

## Karma System (Luck)
- **Karma** represents the player's luck (Base is 10).
- High Karma increases Critical Hit chance (`5% + Karma/20`).
- High Karma increases "Miracle Dodge" chance (completely negating damage).
- Enemies also have Karma based on their Tier (LOW = 5, NORMAL = 10, ELITE = 35, BOSS = 75, FINAL BOSS = 200).

## Skills & Items
- Players can equip **Skills** and **Items** to heal HP, deal instant DMG, or buff/debuff stats (ATK, DEF, AGL, ALL).
- **Skill Usage Limit**: The number of times a player can use skills in a single fight is limited by their level (`3 * floor(level/10)`). Minimum limit is 3.

## Tiers & Enemies
- Enemies scale from LOW, NORMAL, HIGH, ELITE, SUPER ELITE, BOSS, SUPER BOSS, BONUS ENEMY, to FINAL BOSS.
- **Notable Bosses**: The FINAL BOSS tier features multi-phase, extremely difficult threats. BONUS ENEMIES like **Mysterious Figure** have no mercy and use finishing skills early.

## AI Combat Behavior
- Enemies are controlled by RVDiA. They will prioritize offensive skills if they miss frequently, and use "Finisher" skills (like `HP-100%`) only after Turn 10 (unless they are a BONUS ENEMY).

## Directing Users
- If a user asks for specific details about enemies, items, or their stats, **always** point them to use the bot commands!
- Tell them to use `/game enemies` to view the list of enemies.
- Tell them to use `/game account` (or `/game profile`) to view their stats, level, and inventory.
- Remind them they can use `/game help` to see all Re:Volution commands.
