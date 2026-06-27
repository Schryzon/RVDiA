import os
import logging
from datetime import datetime, timezone
from scripts.main import db

STAGE_THRESHOLDS = {
    "stranger": 50,
    "acquaintance": 150,
    "friend": 350,
    "crush": 700,
    "lover": 1000
}

STAGE_ORDER = ["stranger", "acquaintance", "friend", "crush", "lover"]

STAGE_PROMPTS = {
    "stranger": "",
    "acquaintance": "You have chatted with this user a few times. You are slightly warmer and more familiar with them.",
    "friend": "You consider this user a good friend. Be casual, play-tease, and express friendly attachment.",
    "crush": "You have a crush on this user. Be a bit shy, flustered, cute, warm, and tease them affectionately (use 🥺, blushing, or softer pet names like 'sayang', 'cutie').",
    "lover": "This user is your special lover. You love them dearly. Be openly affectionate, comforting, sweet, and use cute couples' terms of endearment (e.g., 'sayangku', 'my love', 'sweetie')."
}

STAGE_LABELS = {
    "en": {
        "stranger": "Stranger 👤",
        "acquaintance": "Acquaintance 🤝",
        "friend": "Friend 🌸",
        "crush": "Crush 💞",
        "lover": "Lover ❤️"
    },
    "id": {
        "stranger": "Orang Asing 👤",
        "acquaintance": "Kenalan 🤝",
        "friend": "Teman 🌸",
        "crush": "Gebetan 💞",
        "lover": "Kekasih ❤️"
    }
}

STAGE_FLAVORS = {
    "en": {
        "stranger": "She doesn't know you very well yet...",
        "acquaintance": "She remembers your name and smiles when you chat.",
        "friend": "She enjoys your company and laughs at your jokes!",
        "crush": "She gets a bit shy and blushes when you talk to her...",
        "lover": "She loves you with all her heart and cherishes every moment."
    },
    "id": {
        "stranger": "Dia belum terlalu mengenalmu...",
        "acquaintance": "Dia mulai mengingat namamu dan tersenyum saat mengobrol.",
        "friend": "Dia menikmati kehadiranmu dan tertawa mendengar candaanmu!",
        "crush": "Dia menjadi agak pemalu dan merona saat kamu berbicara dengannya...",
        "lover": "Dia mencintaimu dengan sepenuh hati dan menghargai setiap detik bersamamu."
    }
}

class RelationshipService:
    async def get_relationship(self, user_id: int):
        """Fetches the relationship profile for the user, or returns None."""
        try:
            return await db.relationship.find_unique(where={'userId': user_id})
        except Exception as e:
            logging.error(f"Error fetching relationship for {user_id}: {e}")
            return None

    async def start_relationship(self, user_id: int) -> bool:
        """Opt-in to relationship tracking. Returns True if created/exists, False on error."""
        try:
            existing = await db.relationship.find_unique(where={'userId': user_id})
            if existing:
                return True
            await db.relationship.create(data={
                'userId': user_id,
                'affinity': 0,
                'stage': 'stranger'
            })
            return True
        except Exception as e:
            logging.error(f"Error starting relationship for {user_id}: {e}")
            return False

    async def add_affinity(self, user_id: int, amount: int) -> tuple[int, str, bool]:
        """Adds affinity, checks for stage promotion, updates database, and returns (affinity, stage, shifted)."""
        try:
            rel = await db.relationship.find_unique(where={'userId': user_id})
            if not rel:
                return 0, "stranger", False

            old_affinity = rel.affinity
            new_affinity = min(1000, max(0, old_affinity + amount))
            
            # Determine new stage
            new_stage = "stranger"
            for stage, limit in STAGE_THRESHOLDS.items():
                if new_affinity >= limit:
                    # Move to next stage criteria
                    current_idx = STAGE_ORDER.index(stage)
                    if current_idx + 1 < len(STAGE_ORDER):
                        new_stage = STAGE_ORDER[current_idx + 1]
                else:
                    if new_affinity < STAGE_THRESHOLDS["stranger"]:
                        new_stage = "stranger"
                    break
            
            # Bound check: if affinity is exactly 1000, stage is "lover"
            if new_affinity == 1000:
                new_stage = "lover"

            # Determine if stage changed
            shifted = False
            anniversary_update = None
            if new_stage != rel.stage:
                shifted = True
                if new_stage == "lover":
                    anniversary_update = datetime.now(timezone.utc)

            # Update DB
            update_data = {
                'affinity': new_affinity,
                'stage': new_stage
            }
            if anniversary_update:
                update_data['anniversary'] = anniversary_update

            await db.relationship.update(
                where={'userId': user_id},
                data=update_data
            )
            return new_affinity, new_stage, shifted
        except Exception as e:
            logging.error(f"Error updating affinity for {user_id}: {e}")
            return 0, "stranger", False

    def get_stage_label(self, stage: str, lang: str = "en") -> str:
        return STAGE_LABELS.get(lang, STAGE_LABELS["en"]).get(stage, stage)

    def get_stage_description(self, stage: str, lang: str = "en") -> str:
        return STAGE_FLAVORS.get(lang, STAGE_FLAVORS["en"]).get(stage, "")

    def get_personality_overlay(self, stage: str) -> str:
        return STAGE_PROMPTS.get(stage, "")

    def get_next_threshold(self, stage: str) -> int:
        return STAGE_THRESHOLDS.get(stage, 1000)

    def get_progress_bar(self, affinity: int, stage: str) -> tuple[str, int]:
        """Generates progress bar string and the target affinity for next stage."""
        if stage == "lover":
            return "`[████████████]`", 1000

        # Get range boundaries
        idx = STAGE_ORDER.index(stage)
        lower_bound = 0 if idx == 0 else STAGE_THRESHOLDS[STAGE_ORDER[idx - 1]]
        upper_bound = STAGE_THRESHOLDS[stage]

        total_range = upper_bound - lower_bound
        progress = affinity - lower_bound
        percentage = max(0.0, min(1.0, progress / total_range)) if total_range > 0 else 1.0

        bar_length = 12
        filled = int(percentage * bar_length)
        empty = bar_length - filled
        bar = "█" * filled + "░" * empty

        return f"`[{bar}]`", upper_bound

relationship_service = RelationshipService()
