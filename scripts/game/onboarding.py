"""
Onboarding DM module.
Sent to new users immediately after /game register completes.
"""

import os
import discord
from scripts.utils.i18n import i18n


class OnboardingView(discord.ui.View):
    def __init__(self, lang: str, bot):
        super().__init__(timeout=None)
        topgg_url = f"https://top.gg/bot/{bot.user.id}/vote"
        saweria_url = os.getenv('SAWERIA_LINK', 'https://saweria.co/Schryzon')
        kofi_url = "https://ko-fi.com/Schryzon"

        self.add_item(discord.ui.Button(
            label=i18n.get(lang, "game.onboarding_btn_vote"),
            emoji="🗳️",
            style=discord.ButtonStyle.link,
            url=topgg_url
        ))
        self.add_item(discord.ui.Button(
            label="Ko-fi ☕",
            style=discord.ButtonStyle.link,
            url=kofi_url
        ))
        self.add_item(discord.ui.Button(
            label="Saweria ❤️",
            style=discord.ButtonStyle.link,
            url=saweria_url
        ))


async def send_onboarding_dm(user: discord.User, lang: str, bot):
    """
    Fire-and-forget DM to a freshly registered user.
    Silently swallows Forbidden if DMs are closed.
    """
    try:
        title = i18n.get(lang, "game.onboarding_title")
        desc = i18n.get(lang, "game.onboarding_desc")

        embed = discord.Embed(title=title, description=desc, color=0x86273d)
        embed.set_thumbnail(url=bot.user.display_avatar.url)

        commands_title = i18n.get(lang, "game.onboarding_commands_title")
        commands_val = (
            "`/game daily` — " + i18n.get(lang, "game.onboarding_cmd_daily") + "\n"
            "`/game profile` — " + i18n.get(lang, "game.onboarding_cmd_profile") + "\n"
            "`/game adventure` — " + i18n.get(lang, "game.onboarding_cmd_adventure") + "\n"
            "`/game battle` — " + i18n.get(lang, "game.onboarding_cmd_battle") + "\n"
            "`/worldboss` — " + i18n.get(lang, "game.onboarding_cmd_worldboss")
        )
        embed.add_field(name=commands_title, value=commands_val, inline=False)

        vote_title = i18n.get(lang, "game.onboarding_vote_title")
        vote_val = i18n.get(lang, "game.onboarding_vote_desc")
        embed.add_field(name=vote_title, value=vote_val, inline=False)

        premium_title = i18n.get(lang, "game.onboarding_premium_title")
        premium_val = i18n.get(lang, "game.onboarding_premium_desc")
        embed.add_field(name=premium_title, value=premium_val, inline=False)

        embed.set_footer(text=i18n.get(lang, "game.onboarding_footer"))

        view = OnboardingView(lang, bot)
        await user.send(embed=embed, view=view)

    except discord.Forbidden:
        pass  # DMs closed — not a hard failure
    except Exception:
        pass  # Never crash the registration flow
