import discord
from discord.ext import commands, tasks
import pymysql
from datetime import datetime
from typing import Union

from . import config
BIRTHDAY_CHANNEL_ID = config.BIRTHDAY_CHANNEL_ID

# ───────────────────────────────
# Database helpers
# ───────────────────────────────

def get_db():
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        autocommit=True
    )

def ensure_birthday_table():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS birthdays (
            user_id BIGINT PRIMARY KEY,
            birthday VARCHAR(5) NOT NULL
        )
    """)
    cursor.close()
    db.close()

ensure_birthday_table()

# ───────────────────────────────
# Pagination View
# ───────────────────────────────

class BirthdayListView(discord.ui.View):
    def __init__(self, embeds, author_id):
        super().__init__(timeout=120)
        self.embeds = embeds
        self.index = 0
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="◀ Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index - 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index + 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.index], view=self)

    @discord.ui.button(label="✖ Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.message:
            await interaction.message.delete()

# ───────────────────────────────
# Birthday Cog
# ───────────────────────────────

class Birthday(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.birthday_check.start()

    def cog_unload(self):
        self.birthday_check.cancel()

    # ──────────────
    # Add birthday
    # ──────────────
    @commands.command(name="addbday")
    @commands.has_any_role(1334950965408956527, 1243560048077049858)
    async def add_birthday(self, ctx: commands.Context, date: str):
        """Add your birthday (DD/MM)"""
        try:
            parsed = datetime.strptime(date, "%d/%m")
            date = f"{parsed.day:02d}/{parsed.month:02d}"
        except ValueError:
            embed = discord.Embed(
                title="Error",
                description="Invalid date format. Use `DD/MM`.",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "REPLACE INTO birthdays (user_id, birthday) VALUES (%s, %s)",
            (ctx.author.id, date)
        )
        cursor.close()
        db.close()

        embed = discord.Embed(
            title="🎂 Birthday Set",
            description=f"<@{ctx.author.id}>'s birthday is set to `{date}`.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    # ──────────────
    # Remove birthday (Owners + Tech)
    # ──────────────
    @commands.command(name="removebday")
    @commands.has_any_role(
        1240455108047671406,  # Owners
        1243929202785386527   # Tech
    )
    async def remove_birthday(self, ctx: commands.Context, user_id: int):
        """Remove a user's birthday by user ID"""

        db = get_db()
        cursor = db.cursor()
        cursor.execute("DELETE FROM birthdays WHERE user_id = %s", (user_id,))
        removed = cursor.rowcount
        cursor.close()
        db.close()

        if removed:
            embed = discord.Embed(
                title="🎂 Birthday Removed",
                description=f"Birthday entry for <@{user_id}> has been removed.",
                color=discord.Color.orange()
            )
        else:
            embed = discord.Embed(
                title="Not Found",
                description=f"No birthday entry found for <@{user_id}>.",
                color=discord.Color.red()
            )

        await ctx.send(embed=embed)

    # ──────────────
    # List birthdays (paginated)
    # ──────────────
    @commands.command(name="bdaylist")
    async def birthday_list(self, ctx: commands.Context):
        db = get_db()
        cursor = db.cursor()
        cursor.execute("SELECT user_id, birthday FROM birthdays")
        rows = cursor.fetchall() or []
        cursor.close()
        db.close()

        if not rows:
            embed = discord.Embed(
                title="🎂 Birthday List",
                description="No birthdays stored.",
                color=discord.Color.yellow()
            )
            await ctx.send(embed=embed)
            return

        entries = []
        for user_id, date in rows:
            day, month = date.split("/")
            day = f"{int(day):02d}"
            month = f"{int(month):02d}"
            entries.append((user_id, f"{day}/{month}", int(month), int(day)))

        entries.sort(key=lambda x: (x[2], x[3]))

        embeds = []
        lines = []
        length = 0

        for user_id, date, _, _ in entries:
            line = f"<@{user_id}> — `{date}`"
            if length + len(line) > 3800:
                embeds.append(
                    discord.Embed(
                        title="🎂 Birthday List 🎂",
                        description="\n".join(lines),
                        color=discord.Color.blue()
                    )
                )
                lines = []
                length = 0

            lines.append(line)
            length += len(line)

        if lines:
            embeds.append(
                discord.Embed(
                    title="🎂 Birthday List 🎂",
                    description="\n".join(lines),
                    color=discord.Color.blue()
                )
            )

        for i, embed in enumerate(embeds, start=1):
            embed.set_footer(text=f"Page {i}/{len(embeds)}")

        view = BirthdayListView(embeds, ctx.author.id)
        await ctx.send(embed=embeds[0], view=view)

    # ──────────────
    # Birthday checker
    # ──────────────
    @tasks.loop(minutes=60)
    async def birthday_check(self):
        today = datetime.utcnow().strftime("%d/%m")

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            "SELECT user_id FROM birthdays WHERE birthday = %s",
            (today,)
        )
        users = cursor.fetchall() or []
        cursor.close()
        db.close()

        channel = self.bot.get_channel(BIRTHDAY_CHANNEL_ID)

        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        for (user_id,) in users:
            await channel.send(
                f"🎂 Happy Birthday <@{user_id}>! 🎉",
                allowed_mentions=discord.AllowedMentions(users=True)
            )


    @birthday_check.before_loop
    async def before_birthday_check(self):
        await self.bot.wait_until_ready()

# ───────────────────────────────
# Setup
# ───────────────────────────────

async def setup(bot: commands.Bot):
    await bot.add_cog(Birthday(bot))
