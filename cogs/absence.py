import asyncio
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta
import pymysql
from . import config

# Use config values
ABSENCE_ROLE_ID = config.ABSENCE_ROLE_ID
ABSENCE_CHANNEL_ID = config.ABSENCE_CHANNEL_ID
STAFF_ALERT_CHANNEL_ID = config.STAFF_ALERT_CHANNEL_ID
MIRROR_GUILD_ID = config.MIRROR_GUILD_ID
MIRROR_CHANNEL_ID = config.MIRROR_CHANNEL_ID
ABSENCE_WARNING_PERIOD = config.ABSENCE_WARNING_PERIOD

# Categories where absent staff are not allowed to send messages (configurable)
try:
    RESTRICTED_CATEGORY_IDS = set(config.ABSENCE_RESTRICTED_CATEGORIES)
except AttributeError:
    # Fallback in case config is not updated
    RESTRICTED_CATEGORY_IDS = {1240456571541258341, 1422566042630230116}

def get_db():
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        autocommit=True
    )

def ensure_absence_table():
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS absences (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                message TEXT NOT NULL,
                start_time DATETIME NOT NULL,
                message_id BIGINT NULL,
                last_warned DATETIME NULL
            )
        """)
        db.commit()
    finally:
        cursor.close()
        db.close()




class Absence(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Ensure DB table exists, but don't let failures prevent cog loading
        try:
            ensure_absence_table()
        except Exception as e:
            print(f"Warning: ensure_absence_table() failed during cog init: {e}")
        self.check_long_absences.start() 

    async def get_mirror_channel(self):
        guild = self.bot.get_guild(MIRROR_GUILD_ID)
        return guild.get_channel(MIRROR_CHANNEL_ID) if guild else None

    # ------------------ $absence command ------------------
    @commands.command(name="absence")
    @commands.has_any_role(1334950965408956527, 1243560048077049858)
    async def add_absence(self, ctx, *, message: str):
        """Mark yourself as absent and notify staff."""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        db = get_db()
        try:
            cursor = db.cursor()

            cursor.execute("SELECT id FROM absences WHERE user_id=%s", (ctx.author.id,))
            if cursor.fetchone():
                await ctx.send("❌ You are already marked as absent.")
                return

            cursor.execute(
                "INSERT INTO absences (user_id, message, start_time, message_id, last_warned) VALUES (%s, %s, %s, NULL, NULL)",
                (ctx.author.id, message, datetime.utcnow())
            )
            absence_id = cursor.lastrowid
            db.commit()

            channel = ctx.guild.get_channel(ABSENCE_CHANNEL_ID)
            if not channel:
                await ctx.send("⚠️ Absences channel not found.")
                return

            mirror_channel = await self.get_mirror_channel()

            await channel.send(f"<@{ctx.author.id}>")
            embed = discord.Embed(
                title="📌 Staff Absence Notice",
                description=f"**{ctx.author.display_name}** is now marked as absent.\n\n**Reason:** {message}",
                color=discord.Color.orange()
            )
            embed.set_footer(text="They will not receive pings during their leave.")
            msg = await channel.send(embed=embed)

            if mirror_channel:
                await mirror_channel.send(embed=embed)

            # Update DB with message_id
            cursor.execute("UPDATE absences SET message_id=%s WHERE id=%s", (msg.id, absence_id))
            db.commit()

            # Assign absence role
            role = ctx.guild.get_role(ABSENCE_ROLE_ID)
            if role:
                try:
                    await ctx.author.add_roles(role, reason="Marked as absent")
                except discord.Forbidden:
                    await channel.send("⚠️ I cannot assign the absence role. Check my permissions and role hierarchy.")

        finally:
            cursor.close()
            db.close()

    # ------------------ $removeabsence command ------------------
    @commands.command(name="removeabsence")
    @commands.has_any_role(1334950965408956527, 1243560048077049858)
    async def remove_absence(self, ctx):
        """Remove your absence and restore notifications."""
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        db = get_db()
        try:
            cursor = db.cursor()
            cursor.execute("SELECT message_id FROM absences WHERE user_id=%s", (ctx.author.id,))
            row = cursor.fetchone()

            if not row:
                await ctx.send("❌ No absence record found for you.")
                return

            message_id = row[0]
            cursor.execute("DELETE FROM absences WHERE user_id=%s", (ctx.author.id,))
            db.commit()

            # Remove role
            role = ctx.guild.get_role(ABSENCE_ROLE_ID)
            if role:
                try:
                    await ctx.author.remove_roles(role, reason="Returned from absence")
                except discord.Forbidden:
                    pass

            # Update embed in channel
            channel = ctx.guild.get_channel(ABSENCE_CHANNEL_ID)
            mirror_channel = await self.get_mirror_channel()
            if channel:
                try:
                    msg = await channel.fetch_message(message_id)
                    embed = msg.embeds[0]
                    embed.title = "✅ STAFF HAS RETURNED"
                    embed.color = discord.Color.green()
                    embed.description = f"**{ctx.author.display_name}** has returned from absence!"
                    await msg.edit(embed=embed)

                    if mirror_channel:
                        await mirror_channel.send(embed=embed)

                    ping_msg = await channel.send(f"<@{ctx.author.id}>")
                    await ping_msg.delete()
                except Exception:
                    fallback_embed = discord.Embed(
                        title="✅ STAFF HAS RETURNED",
                        description=f"**{ctx.author.display_name}** has returned from absence!",
                        color=discord.Color.green()
                    )
                    await channel.send(embed=fallback_embed)
                    if mirror_channel:
                        await mirror_channel.send(embed=fallback_embed)
        finally:
            cursor.close()
            db.close()

    # ------------------ Long absence checker ------------------
    @tasks.loop(hours=24)
    async def check_long_absences(self):
        """Check for staff on leave longer than 2 months."""
        db = get_db()
        try:
            cursor = db.cursor()
            cursor.execute("SELECT user_id, start_time, message, last_warned FROM absences")
            rows = cursor.fetchall()
        finally:
            cursor.close()
            db.close()

        now = datetime.utcnow()
        alert_channel = self.bot.get_channel(STAFF_ALERT_CHANNEL_ID)
        if not alert_channel:
            return

        for user_id, start_time, reason, last_warned in rows:
            if (now - start_time).days >= ABSENCE_WARNING_PERIOD:
                member = None
                for guild in self.bot.guilds:
                    member = guild.get_member(user_id)
                    if member:
                        break
                if not member:
                    continue

                should_warn = (
                    last_warned is None or
                    (now - last_warned).days >= ABSENCE_WARNING_PERIOD
                )

                if should_warn:
                    try:
                        dm_embed = discord.Embed(
                            title="## <:zExclaim:1244645794909392926> Staff Activity Notice",
                            description=(
                                "We’re looking for active moderators to help keep **Cheesecake Art Cafe** running smoothly. "
                                "If you’re part of the staff, it’s important to stay involved—being inactive for more than 2 months "
                                "might affect how reliable you’re seen when it comes to helping out.\n\n"
                                "**If you’re having trouble staying active or keeping up with mod duties, here’s what you can do:**\n"
                                "- Thinking of stepping down from the staff team? Message an owner and let them know—it’s totally okay to move on if you can’t stay active.\n"
                                "- If you’re just struggling a bit and need support, reach out to an owner. We’re here to help you get back on track."
                            ),
                            color=discord.Color.orange()
                        )
                        dm_embed.set_author(name="Cheesecake Art Cafe", icon_url="https://cdn.discordapp.com/emojis/1244645794909392926.png?size=96")
                        await member.send(embed=dm_embed)

                        db2 = get_db()
                        try:
                            cursor2 = db2.cursor()
                            cursor2.execute("UPDATE absences SET last_warned=%s WHERE user_id=%s", (now, user_id))
                            db2.commit()
                        finally:
                            cursor2.close()
                            db2.close()
                    except discord.Forbidden:
                        pass

                # Post info in alert channel
                absence_date = start_time.strftime("%d/%m/%Y")
                reason_text = reason if reason else "No reason provided"
                alert_embed = discord.Embed(
                    title="⚠️ Staff on Extended Leave",
                    color=discord.Color.red()
                )
                alert_embed.add_field(name="Username", value=str(member), inline=True)
                alert_embed.add_field(name="User ID", value=str(user_id), inline=True)
                alert_embed.add_field(name="Start Date", value=absence_date, inline=True)
                alert_embed.add_field(name="Reason", value=reason_text, inline=False)

                await alert_channel.send(embed=alert_embed)

    @check_long_absences.before_loop
    async def before_check_long_absences(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message):
        # Ignore DMs and messages from bots
        if message.author.bot or not message.guild:
            return

        channel = message.channel
        # Only enforce in specific categories
        if getattr(channel, "category_id", None) not in RESTRICTED_CATEGORY_IDS:
            return

        guild = message.guild
        absence_role = guild.get_role(ABSENCE_ROLE_ID)
        # Check if author has the absence role
        if absence_role and absence_role in message.author.roles:
            try:
                await message.delete()
            except discord.Forbidden:
                # Bot lacks permissions to delete the message
                return
            try:
                temp = await channel.send(f"<@{message.author.id}> You are on vacation, you should not be working")
                # delete the temp message after a short delay
                await asyncio.sleep(8)
                await temp.delete()
            except Exception:
                pass


async def setup(bot):
    await bot.add_cog(Absence(bot))
    print("✅ Loaded cog: absence")