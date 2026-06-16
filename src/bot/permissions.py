"""
Role-based permission helpers for Discord slash commands.

Three named roles form a strict hierarchy (highest → lowest):
  Guildmaster > Moderators > Draft League Coaches

Any role satisfies the check for all tiers below it.
Manage Guild permission is always accepted as a safety net.
"""
import discord
from discord import app_commands

ROLE_GUILDMASTER = "Guildmaster"
ROLE_MOD         = "Moderators"
ROLE_COACH       = "Draft League Coaches"

_TIERS: dict[str, tuple[str, ...]] = {
    ROLE_COACH:       (ROLE_COACH, ROLE_MOD, ROLE_GUILDMASTER),
    ROLE_MOD:         (ROLE_MOD, ROLE_GUILDMASTER),
    ROLE_GUILDMASTER: (ROLE_GUILDMASTER,),
}


def require_role(min_role: str) -> app_commands.check:
    """Return a slash-command check decorator requiring min_role or higher.

    Higher-tier roles always satisfy lower-tier checks. Manage Guild is accepted
    unconditionally so a misconfigured role list can never lock out the server owner.
    """
    accepted = frozenset(_TIERS[min_role])

    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            raise app_commands.CheckFailure("This command can only be used in a server.")
        if interaction.user.guild_permissions.manage_guild:
            return True
        if {r.name for r in interaction.user.roles} & accepted:
            return True
        raise app_commands.CheckFailure(
            f"You need the **{min_role}** role (or higher) to use this command."
        )

    return app_commands.check(predicate)
