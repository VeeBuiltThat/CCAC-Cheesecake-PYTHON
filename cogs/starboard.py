import discord
from discord.ext import commands
import pymysql
from datetime import datetime
from discord import TextChannel
from . import config
ART_SHOWCASE_ID = config.ART_SHOWCASE_ID
SERVER_FANART_ID = config.SERVER_FANART_ID
STARBOARD_ID = config.STARBOARD_ID
CUSTOM_EMOJI = config.CUSTOM_EMOJI
SMALL_THUMBNAIL = config.SMALL_THUMBNAIL
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

def ensure_starboard_table():
    db = get_db()
    try:
        with db.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS starboard (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    message_id BIGINT NOT NULL UNIQUE,
                    author_id BIGINT NOT NULL,
                    posted_at DATETIME NOT NULL
                )
            """)
            db.commit()
    finally:
        db.close()

ensure_starboard_table()

class Starboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.channel.id not in [ART_SHOWCASE_ID, SERVER_FANART_ID]:
            return

        has_media = bool(message.attachments) or any(
            embed.type in ("image", "video") or embed.thumbnail or embed.image
            for embed in message.embeds
        )
        if not has_media:
            return

        try:
            emoji = discord.PartialEmoji.from_str(CUSTOM_EMOJI)
            await message.add_reaction(emoji)
        except Exception as e:
            print(f"Failed to react: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.channel_id not in [ART_SHOWCASE_ID, SERVER_FANART_ID]:
            return
        if str(payload.emoji) != CUSTOM_EMOJI:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        db = get_db()
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT 1 FROM starboard WHERE message_id=%s", (message.id,))
                if cursor.fetchone():
                    return
        finally:
            db.close()

        for reaction in message.reactions:
            if str(reaction.emoji) == CUSTOM_EMOJI and reaction.count >= 5:
                await self.send_to_starboard(message)
                break

    async def send_to_starboard(self, message: discord.Message):
        starboard_channel = self.bot.get_channel(STARBOARD_ID)
        if not starboard_channel:
            return

        channel_mention = message.channel.mention if isinstance(message.channel, TextChannel) else getattr(message.channel, "name", "DM")

        content = message.content
        if content and len(content) > 1024:
            content = content[:1020] + "..."

        embed = discord.Embed(
            title="🌟 ARTIST SHOUTOUT 🌟",
            description=f"From {channel_mention} • [Jump to Post]({message.jump_url})",
            color=discord.Color.from_rgb(255, 105, 180),
            timestamp=datetime.utcnow()
        )

        embed.set_author(
            name=message.author.display_name,
            icon_url=getattr(message.author.display_avatar, "url", None)
        )
        embed.set_thumbnail(url=SMALL_THUMBNAIL)

        if content:
            embed.add_field(name="Message", value=content, inline=False)

        if message.attachments:
            embed.set_image(url=message.attachments[0].url)

        for reaction in message.reactions:
            if str(reaction.emoji) == CUSTOM_EMOJI:
                embed.set_footer(text=f"{CUSTOM_EMOJI} {reaction.count} votes")
                break

        await starboard_channel.send(embed=embed)

        db = get_db()
        try:
            with db.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO starboard (message_id, author_id, posted_at) VALUES (%s, %s, %s)",
                    (message.id, message.author.id, datetime.utcnow())
                )
                db.commit()
        finally:
            db.close()

async def setup(bot):
    await bot.add_cog(Starboard(bot))
