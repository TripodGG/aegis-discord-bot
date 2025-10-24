import os, json, time, pathlib
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

# Load .env (expects DISCORD_TOKEN, optional GUILD_ID)
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
TEST_GUILD_ID = int(os.getenv("GUILD_ID")) if os.getenv("GUILD_ID") else None

INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.guilds = True

CONFIG_DIR = pathlib.Path("./config")
CONFIG_DIR.mkdir(exist_ok=True)

def cfg_path(guild_id: int) -> pathlib.Path:
    return CONFIG_DIR / f"{guild_id}.json"

def load_cfg(guild_id: int) -> dict:
    p = cfg_path(guild_id)
    if p.exists():
        try:
            return json.loads(p.read_text("utf-8"))
        except Exception:
            return {}
    return {}

def save_cfg(guild_id: int, data: dict) -> None:
    cfg_path(guild_id).write_text(json.dumps(data, indent=2), encoding="utf-8")

def get_role_mentions(guild: discord.Guild, role_ids: list[int]) -> str:
    roles = [guild.get_role(rid) for rid in (role_ids or [])]
    return ", ".join(r.mention for r in roles if r)

def get_channel_mention(guild: discord.Guild, channel_id: int | None) -> str:
    if not channel_id:
        return "Not set"
    ch = guild.get_channel(channel_id)
    return ch.mention if isinstance(ch, discord.TextChannel) else "Not set"

def member_has_any_role(member: discord.Member, role_ids: list[int]) -> bool:
    if not role_ids:
        return False
    member_role_ids = {r.id for r in member.roles}
    return any(rid in member_role_ids for rid in role_ids)

def can_use_commands(member: discord.Member, cfg: dict) -> tuple[bool, str]:
    allowed = cfg.get("allowed_role_ids", [])
    excluded = cfg.get("excluded_role_ids", [])
    if not allowed:
        return (False, "No allowed roles are configured yet. Ask an admin to run `/setup`.")
    if not isinstance(member, discord.Member):
        return (False, "Use this in a server.")
    if not member_has_any_role(member, allowed):
        return (False, "You don’t have a required role to use this command.")
    if excluded and member_has_any_role(member, excluded):
        return (False, "Your role is excluded from using this command.")
    return (True, "")

async def log_action(guild: discord.Guild, cfg: dict, content: str, embed: discord.Embed | None = None):
    log_channel_id = cfg.get("log_channel_id")
    if not log_channel_id:
        return
    ch = guild.get_channel(log_channel_id)
    if isinstance(ch, discord.TextChannel):
        await ch.send(content=content, embed=embed, allowed_mentions=discord.AllowedMentions(roles=True, users=True, everyone=False))

# ---------------- UI Components ----------------

class RolesSelect(discord.ui.Select):
    def __init__(self, placeholder: str, preselected: list[int] | None = None, max_values: int = 25, row: int = 0):
        super().__init__(placeholder=placeholder, min_values=0, max_values=max_values, options=[], row=row)
        self.preselected = set(preselected or [])

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

class ChannelsSelect(discord.ui.Select):
    def __init__(self, placeholder: str, allow_none: bool, preselected: int | None, row: int):
        super().__init__(placeholder=placeholder, min_values=0 if allow_none else 1, max_values=1, options=[], row=row)
        self.allow_none = allow_none
        self.preselected = preselected

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

class SetupView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, cfg: dict, invoker: discord.Member, timeout: float = 600):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.guild = guild
        self.cfg = cfg.copy()
        self.invoker = invoker

        allowed_ids = set(self.cfg.get("allowed_role_ids", []))
        excluded_ids = set(self.cfg.get("excluded_role_ids", []))
        admiral_id = self.cfg.get("admiral_role_id")
        war_channel_id = self.cfg.get("war_channel_id")
        log_channel_id = self.cfg.get("log_channel_id")

        # Allowed roles
        self.allowed_select = RolesSelect("Allowed Roles (who can use commands)", list(allowed_ids), row=0)
        allowed_opts = []
        for r in sorted(guild.roles, key=lambda x: x.position, reverse=True):
            if r.is_default(): continue
            allowed_opts.append(discord.SelectOption(label=r.name[:95], value=str(r.id), default=(r.id in allowed_ids)))
        self.allowed_select.options = allowed_opts

        # Excluded roles
        self.excluded_select = RolesSelect("Excluded Roles (block these)", list(excluded_ids), row=1)
        excluded_opts = []
        for r in sorted(guild.roles, key=lambda x: x.position, reverse=True):
            if r.is_default(): continue
            excluded_opts.append(discord.SelectOption(label=r.name[:95], value=str(r.id), default=(r.id in excluded_ids)))
        self.excluded_select.options = excluded_opts

        # Admiral role (single select, allow none)
        self.admiral_select = RolesSelect("Admiral Role (optional, pinged on /declare)", [admiral_id] if admiral_id else [], max_values=1, row=2)
        admiral_opts = [discord.SelectOption(label="None", value="none", default=(admiral_id is None))]
        for r in sorted(guild.roles, key=lambda x: x.position, reverse=True):
            if r.is_default(): continue
            admiral_opts.append(discord.SelectOption(label=r.name[:95], value=str(r.id), default=(r.id == admiral_id)))
        self.admiral_select.options = admiral_opts

        # War channel
        self.war_select = ChannelsSelect("War Declaration Channel (optional)", allow_none=True, preselected=war_channel_id, row=3)
        war_opts = [discord.SelectOption(label="None", value="none", default=(war_channel_id is None))]
        for ch in guild.text_channels:
            war_opts.append(discord.SelectOption(label=f"#{ch.name}"[:95], value=str(ch.id), default=(ch.id == war_channel_id)))
        self.war_select.options = war_opts

        # Log channel (required)
        self.log_select = ChannelsSelect("Log Channel (required, recommend private)", allow_none=False, preselected=log_channel_id, row=4)
        log_opts = []
        for ch in guild.text_channels:
            log_opts.append(discord.SelectOption(label=f"#{ch.name}"[:95], value=str(ch.id), default=(ch.id == log_channel_id)))
        self.log_select.options = log_opts

        # Buttons
        self.save_btn = discord.ui.Button(style=discord.ButtonStyle.success, label="Save", row=5)
        self.cancel_btn = discord.ui.Button(style=discord.ButtonStyle.secondary, label="Cancel", row=5)
        self.save_btn.callback = self.save
        self.cancel_btn.callback = self.cancel

        # Add items
        self.add_item(self.allowed_select)
        self.add_item(self.excluded_select)
        self.add_item(self.admiral_select)
        self.add_item(self.war_select)
        self.add_item(self.log_select)
        self.add_item(self.save_btn)
        self.add_item(self.cancel_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.invoker.id:
            return True
        if isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator:
            return True
        await interaction.response.send_message("This setup panel is locked to the admin who opened it.", ephemeral=True)
        return False

    async def save(self, interaction: discord.Interaction):
        allowed = [int(v) for v in self.allowed_select.values] if self.allowed_select.values else []
        excluded = [int(v) for v in self.excluded_select.values] if self.excluded_select.values else []

        # Admiral role (handle "None")
        admiral_role_id = None
        if self.admiral_select.values:
            val = self.admiral_select.values[0]
            if val != "none":
                admiral_role_id = int(val)

        # War channel
        war_channel_id = None
        if self.war_select.values and self.war_select.values[0] != "none":
            war_channel_id = int(self.war_select.values[0])

        # Log channel (required)
        if not self.log_select.values:
            return await interaction.response.send_message("Please select a **Log Channel**.", ephemeral=True)
        log_channel_id = int(self.log_select.values[0])

        new_cfg = {
            "allowed_role_ids": allowed,
            "excluded_role_ids": excluded,
            "admiral_role_id": admiral_role_id,
            "war_channel_id": war_channel_id,
            "log_channel_id": log_channel_id,
            "updated_by": interaction.user.id,
            "updated_at": int(time.time())
        }
        save_cfg(self.guild.id, new_cfg)

        summary = (
            f"**Allowed:** {get_role_mentions(self.guild, allowed) or '_none_'}\n"
            f"**Excluded:** {get_role_mentions(self.guild, excluded) or '_none_'}\n"
            f"**Admiral Role:** {(self.guild.get_role(admiral_role_id).mention if admiral_role_id and self.guild.get_role(admiral_role_id) else 'Not set')}\n"
            f"**War Channel:** {get_channel_mention(self.guild, war_channel_id)}\n"
            f"**Log Channel:** {get_channel_mention(self.guild, log_channel_id)}"
        )
        await interaction.response.edit_message(content="✅ **Configuration saved.**\n" + summary, view=None)
        await log_action(self.guild, new_cfg, f"🛠️ Configuration updated by {interaction.user.mention}.\n{summary}")

    async def cancel(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Setup canceled. No changes saved.", view=None)

# ---------------- Bot / Commands (with Modals) ----------------

class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if TEST_GUILD_ID:
            guild_obj = discord.Object(id=TEST_GUILD_ID)
            self.tree.copy_global_to(guild=guild_obj)
            await self.tree.sync(guild=guild_obj)
        else:
            await self.tree.sync()

bot = Bot()

def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        member = interaction.user
        if isinstance(member, discord.Member) and member.guild_permissions.administrator:
            return True
        await interaction.response.send_message("Admin only.", ephemeral=True)
        return False
    return app_commands.check(predicate)

@bot.tree.command(name="setup", description="Configure allowed/excluded roles, admiral role, and channels.")
@admin_only()
async def setup_cmd(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        return await interaction.response.send_message("Use this in a server.", ephemeral=True)
    cfg = load_cfg(guild.id)
    view = SetupView(bot, guild, cfg, interaction.user)
    await interaction.response.send_message(
        content=(
            "🔧 **Server Setup**\n"
            "Choose Allowed/Excluded Roles, **Admiral Role** (optional), War Channel (optional), and a **Log Channel** (required).\n"
            "_Tip: Make the log channel private for staff only._"
        ),
        view=view,
        ephemeral=True
    )

@bot.tree.command(name="config", description="Show current configuration (ephemeral).")
async def config_show(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        return await interaction.response.send_message("Use this in a server.", ephemeral=True)
    cfg = load_cfg(guild.id)
    if not cfg:
        return await interaction.response.send_message("No configuration saved yet. Ask an admin to run `/setup`.", ephemeral=True)
    admiral_role_id = cfg.get('admiral_role_id')
    admiral_txt = (guild.get_role(admiral_role_id).mention if admiral_role_id and guild.get_role(admiral_role_id) else "Not set")
    summary = (
        f"**Allowed:** {get_role_mentions(guild, cfg.get('allowed_role_ids', [])) or '_none_'}\n"
        f"**Excluded:** {get_role_mentions(guild, cfg.get('excluded_role_ids', [])) or '_none_'}\n"
        f"**Admiral Role:** {admiral_txt}\n"
        f"**War Channel:** {get_channel_mention(guild, cfg.get('war_channel_id'))}\n"
        f"**Log Channel:** {get_channel_mention(guild, cfg.get('log_channel_id'))}\n"
        f"_Updated: <t:{cfg.get('updated_at', 0)}:R> by <@{cfg.get('updated_by', 0)}>_"
    )
    await interaction.response.send_message(summary, ephemeral=True)

def require_configured_access():
    async def predicate(interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        if not guild:
            await interaction.response.send_message("Use in a server.", ephemeral=True)
            return False
        cfg = load_cfg(guild.id)
        ok, msg = can_use_commands(interaction.user, cfg)
        if not ok:
            await interaction.response.send_message(msg, ephemeral=True)
            return False
        return True
    return app_commands.check(predicate)

# ---------- Modals ----------

class LongReasonModal(discord.ui.Modal, title="Provide Details"):
    reason = discord.ui.TextInput(
        label="Reason / Details",
        style=discord.TextStyle.paragraph,
        placeholder="Provide all relevant info…",
        required=True,
        max_length=4000,
        row=0
    )
    def __init__(self, on_submit_callback):
        super().__init__(timeout=300)
        self._on_submit_callback = on_submit_callback

    async def on_submit(self, interaction: discord.Interaction):
        await self._on_submit_callback(interaction, str(self.reason))

# ---------- /roe (with modal + role ping) ----------

@bot.tree.command(name="roe", description="Report a Rules of Engagement violation (pings selected role).")
@require_configured_access()
@app_commands.describe(offender="Offending player", target_role="Role to notify/ping (e.g., their alliance)")
async def roe(interaction: discord.Interaction, offender: discord.Member, target_role: discord.Role):
    guild = interaction.guild
    cfg = load_cfg(guild.id)

    async def after_modal_submit(modal_inter: discord.Interaction, reason_text: str):
        ts = int(time.time())
        embed = discord.Embed(
            title="🚨 RoE Violation Report",
            color=discord.Color.red(),
            description=(
                f"**Offender:** {offender.mention}\n"
                f"**Reported by:** {interaction.user.mention}\n"
                f"**Details:** {reason_text}\n"
                f"**When:** <t:{ts}:F>"
            )
        )
        content = target_role.mention  # ping target role
        msg = await interaction.channel.send(
            content=content,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True, users=True, everyone=False)
        )
        await modal_inter.response.send_message(f"Posted in {interaction.channel.mention} (jump: {msg.jump_url}).", ephemeral=True)
        await log_action(guild, cfg, f"RoE reported by {interaction.user.mention} against {offender.mention} | Pinged {target_role.mention} in {interaction.channel.mention}.")

    await interaction.response.send_modal(LongReasonModal(after_modal_submit))

# ---------- /declare (with modal + pings + war channel) ----------

@bot.tree.command(name="declare", description="Declare war against a role/faction with a detailed reason.")
@require_configured_access()
@app_commands.describe(target="Role/faction to declare against")
async def declare(interaction: discord.Interaction, target: discord.Role):
    guild = interaction.guild
    cfg = load_cfg(guild.id)
    admiral_role_id = cfg.get("admiral_role_id")
    admiral_role = guild.get_role(admiral_role_id) if admiral_role_id else None
    war_channel_id = cfg.get("war_channel_id")
    war_channel = guild.get_channel(war_channel_id) if war_channel_id else None

    async def after_modal_submit(modal_inter: discord.Interaction, reason_text: str):
        ts = int(time.time())
        embed = discord.Embed(
            title="🛡️ War Declaration",
            color=discord.Color.orange(),
            description=(
                f"**Declaring Against:** {target.mention}\n"
                f"**Declared by:** {interaction.user.mention}\n"
                f"**Reason:** {reason_text}\n"
                f"**When:** <t:{ts}:F>"
            )
        )

        # Build content to ping: target + admiral
        mentions = [target.mention]
        if admiral_role:
            mentions.append(admiral_role.mention)
        content = " ".join(mentions) if mentions else None

        # Post here
        here = await interaction.channel.send(
            content=content,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(roles=True, users=True, everyone=False)
        )

        msg_links = [f"{interaction.channel.mention} (jump: {here.jump_url})"]
        # Also post in war channel if configured
        if isinstance(war_channel, discord.TextChannel):
            there = await war_channel.send(
                content=content,
                embed=embed,
                allowed_mentions=discord.AllowedMentions(roles=True, users=True, everyone=False)
            )
            msg_links.append(f"{war_channel.mention} (jump: {there.jump_url})")

        await modal_inter.response.send_message("Posted: " + " and ".join(msg_links), ephemeral=True)
        await log_action(
            guild, cfg,
            f"War declared by {interaction.user.mention} vs {target.mention}. "
            f"Pings: {content or 'none'}. Posted to: " + ", ".join(msg_links)
        )

    await interaction.response.send_modal(LongReasonModal(after_modal_submit))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (id: {bot.user.id}) — Aegis standing by.")

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("DISCORD_TOKEN missing. Set it in .env or environment.")
    bot.run(TOKEN)
