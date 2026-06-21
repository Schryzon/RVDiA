import random
from datetime import datetime, timedelta, timezone
from prisma import Json
from scripts.main import db
from scripts.game.game import give_rewards

# Boss templates for random generation
BOSS_TEMPLATES = [
    {"name": "Dream Devourer", "tier": "BOSS", "max_hp": 3000, "base_coins": 1000, "base_exp": 500},
    {"name": "Phantasm Drake", "tier": "ELITE BOSS", "max_hp": 6000, "base_coins": 2000, "base_exp": 1000},
    {"name": "Shadow Nightmare", "tier": "SUPER BOSS", "max_hp": 12000, "base_coins": 4500, "base_exp": 2200},
    {"name": "Abyss Monarch", "tier": "FINAL BOSS", "max_hp": 25000, "base_coins": 10000, "base_exp": 5000}
]

async def get_active_boss():
    """
    Fetches the active World Boss, or generates a new one if none exists or has expired (24h).
    """
    boss = await db.worldboss.find_first(
        where={"isActive": True}
    )

    now = datetime.now(timezone.utc)

    # Generate a new boss if none exists, or the active one is older than 24 hours
    if not boss or (now - boss.lastResetTime) > timedelta(hours=24):
        if boss:
            # Mark the expired boss as inactive
            await db.worldboss.update(
                where={"id": boss.id},
                data={"isActive": False}
            )
            
        template = random.choice(BOSS_TEMPLATES)
        rewards_config = {
            "coins": template["base_coins"],
            "exp": template["base_exp"]
        }

        boss = await db.worldboss.create(
            data={
                "name": template["name"],
                "tier": template["tier"],
                "hp": template["max_hp"],
                "maxHp": template["max_hp"],
                "isActive": True,
                "rewards": Json(rewards_config),
                "lastResetTime": now
            }
        )

    return boss

async def attack_boss(user_id: int, username: str, damage: int) -> dict:
    """
    Applies damage to the active World Boss and updates player contribution.
    Returns details about the hit and whether the boss was defeated.
    """
    boss = await get_active_boss()
    
    # Make sure damage does not exceed boss's remaining HP
    actual_damage = min(damage, boss.hp)
    new_hp = boss.hp - actual_damage

    # Update or insert contribution record
    contribution = await db.worldbosscontribution.find_unique(
        where={"bossId_userId": {"bossId": boss.id, "userId": user_id}}
    )

    if contribution:
        await db.worldbosscontribution.update(
            where={"id": contribution.id},
            data={
                "damage": contribution.damage + actual_damage,
                "lastHitTime": datetime.now(timezone.utc)
            }
        )
    else:
        await db.worldbosscontribution.create(
            data={
                "bossId": boss.id,
                "userId": user_id,
                "username": username,
                "damage": actual_damage,
                "lastHitTime": datetime.now(timezone.utc)
            }
        )

    # Update boss HP in db
    is_defeated = new_hp <= 0
    await db.worldboss.update(
        where={"id": boss.id},
        data={
            "hp": new_hp,
            "isActive": not is_defeated
        }
    )

    rewards_distributed = []
    if is_defeated:
        rewards_distributed = await distribute_rewards(boss)

    return {
        "boss_name": boss.name,
        "damage_dealt": actual_damage,
        "boss_remaining_hp": new_hp,
        "is_defeated": is_defeated,
        "rewards_distributed": rewards_distributed
    }

async def distribute_rewards(boss) -> list:
    """
    Distributes rewards proportionally to all contributors.
    """
    contributions = await db.worldbosscontribution.find_many(
        where={"bossId": boss.id}
    )

    if not contributions:
        return []

    total_damage = sum(c.damage for c in contributions)
    if total_damage == 0:
        total_damage = 1

    rewards_config = boss.rewards
    total_coins = rewards_config.get("coins", 1000)
    total_exp = rewards_config.get("exp", 500)

    distributed = []

    for c in contributions:
        # Calculate proportional share
        share = c.damage / total_damage
        share_coins = max(50, round(total_coins * share))
        share_exp = max(20, round(total_exp * share))

        # Award to player database record
        user_record = await db.user.find_unique(where={"id": c.userId})
        if user_record:
            data = user_record.data
            data["coins"] = data.get("coins", 0) + share_coins
            data["exp"] = data.get("exp", 0) + share_exp

            await db.user.update(
                where={"id": c.userId},
                data={"data": Json(data)}
            )

            # Check if user leveled up
            from scripts.game.game import level_up
            await level_up(user_record)

            distributed.append({
                "userId": str(c.userId),
                "username": c.username,
                "damage": c.damage,
                "share": round(share * 100, 1),
                "coins": share_coins,
                "exp": share_exp
            })

    return distributed

async def force_spawn_boss(name: str = None, tier: str = None, max_hp: int = None):
    """
    Forcefully deactivates the current active boss and spawns a new custom or template-based boss.
    """
    # Deactivate active bosses
    await db.worldboss.update_many(
        where={"isActive": True},
        data={"isActive": False}
    )

    if name and tier and max_hp:
        template = {
            "name": name,
            "tier": tier,
            "max_hp": max_hp,
            "base_coins": int(max_hp * 0.4),
            "base_exp": int(max_hp * 0.2)
        }
    else:
        template = random.choice(BOSS_TEMPLATES)

    rewards_config = {
        "coins": template["base_coins"],
        "exp": template["base_exp"]
    }

    boss = await db.worldboss.create(
        data={
            "name": template["name"],
            "tier": template["tier"],
            "hp": template["max_hp"],
            "maxHp": template["max_hp"],
            "isActive": True,
            "rewards": Json(rewards_config),
            "lastResetTime": datetime.now(timezone.utc)
        }
    )
    return boss

