import re
import discord
from discord.ext import commands
from typing import Optional
import pymysql
from . import config
DB_HOST = config.DB_HOST
DB_PORT = config.DB_PORT
DB_USER = config.DB_USER
DB_PASSWORD = config.DB_PASSWORD
DB_NAME = config.DB_NAME

def get_db():
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        autocommit=True
    )

def ensure_reaction_roles_table():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reaction_roles (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    message_id BIGINT NOT NULL,
                    role_id BIGINT NOT NULL,
                    emoji VARCHAR(100) NOT NULL,
                    UNIQUE(guild_id, message_id, emoji)
                )
            """)
            db.commit()
    finally:
        db.close()

ensure_reaction_roles_table()


def normalize_emoji_str(emoji: str) -> str:
    try:
        pe = discord.PartialEmoji.from_str(emoji)
        return str(pe)
    except Exception:
        return emoji

def extract_ids_from_role_input(role_input: str) -> Optional[int]:
    m = re.search(r'(\d{17,19})', role_input)
    return int(m.group(1)) if m else None

def parse_message_reference(ref: str):
    try:
        if ref.startswith("http"):
            parts = ref.rstrip("/").split("/")
            guild_id = int(parts[-3])
            channel_id = int(parts[-2])
            message_id = int(parts[-1])
            return guild_id, channel_id, message_id
        if "/" in ref:
            parts = ref.split("/")
            if len(parts) == 3:
                guild_id = int(parts[0])
                channel_id = int(parts[1])
                message_id = int(parts[2])
                return guild_id, channel_id, message_id
        return None, None, int(ref)
    except Exception:
        return None, None, None


class ReactionRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="reaction")
    @commands.has_permissions(manage_roles=True)
    async def add_reaction_role(self, ctx, message_ref: str, role_input: str, emoji: str):
        guild_id, channel_id, message_id = parse_message_reference(message_ref)
        if message_id is None:
            return await ctx.send("❌ Could not parse message reference.")

        target_guild = self.bot.get_guild(guild_id) if guild_id else ctx.guild
        if not target_guild:
            return await ctx.send("❌ Could not determine target guild.")

        target_channel, target_message = None, None
        if channel_id:
            target_channel = target_guild.get_channel(channel_id)
            try:
                target_message = await target_channel.fetch_message(message_id)
            except Exception:
                return await ctx.send("❌ Could not fetch target message.")
        else:
            for ch in target_guild.text_channels:
                try:
                    target_message = await ch.fetch_message(message_id)
                    target_channel = ch
                    break
                except Exception:
                    continue
            if target_message is None:
                return await ctx.send("❌ Could not find message in accessible channels.")

        role_obj = target_guild.get_role(extract_ids_from_role_input(role_input)) or \
                   discord.utils.get(target_guild.roles, name=role_input)
        if not role_obj:
            return await ctx.send("❌ Could not find role in target guild.")

        emoji_str = normalize_emoji_str(emoji)

        db = get_db()
        try:
            with db.cursor() as cursor:
                cursor.execute(
                    "INSERT IGNORE INTO reaction_roles (guild_id, message_id, role_id, emoji) VALUES (%s, %s, %s, %s)",
                    (target_guild.id, message_id, role_obj.id, emoji_str)
                )
                db.commit()
        finally:
            db.close()

        try:
            await target_message.add_reaction(emoji_str)
        except Exception as e:
            return await ctx.send(f"❌ Failed to add reaction: {e}")

        await ctx.send(f"✅ Reaction role added on **{target_guild.name}**: {emoji_str} → **{role_obj.name}**")

    async def get_role_for_reaction(self, guild_id: int, message_id: int, emoji: str) -> Optional[int]:
        emoji_str = normalize_emoji_str(emoji)
        db = get_db()
        try:
            with db.cursor() as cursor:
                cursor.execute(
                    "SELECT role_id FROM reaction_roles WHERE guild_id=%s AND message_id=%s AND emoji=%s",
                    (guild_id, message_id, emoji_str)
                )
                result = cursor.fetchone()
                return result[0] if result else None
        finally:
            db.close()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or payload.user_id == self.bot.user.id:
            return
        role_id = await self.get_role_for_reaction(payload.guild_id, payload.message_id, str(payload.emoji))
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        role = guild.get_role(role_id)
        if member and role:
            try:
                await member.add_roles(role, reason="Reaction role")
            except Exception as e:
                print(f"Failed to add role: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.guild_id is None or payload.user_id == self.bot.user.id:
            return
        role_id = await self.get_role_for_reaction(payload.guild_id, payload.message_id, str(payload.emoji))
        if not role_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id) or await guild.fetch_member(payload.user_id)
        role = guild.get_role(role_id)
        if member and role:
            try:
                await member.remove_roles(role, reason="Reaction role removed")
            except Exception as e:
                print(f"Failed to remove role: {e}")

    @commands.Cog.listener()
    async def on_ready(self):
        print("✅ ReactionRoles cog loaded and ready.")

async def setup(bot):
    await bot.add_cog(ReactionRoles(bot))
