import discord
from discord.ext import commands
from discord.ui import View, Button
from datetime import datetime, timedelta
import pymysql
import random
import asyncio
from . import config

def get_db():
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        autocommit=True
    )

def ensure_giveaway_table():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS giveaways (
            id INT AUTO_INCREMENT PRIMARY KEY,
            host_id BIGINT,
            channel_id BIGINT,
            duration_minutes INT,
            winners INT,
            prizes TEXT,
            message TEXT,
            start_time DATETIME,
            end_time DATETIME
        )
    """)
    cursor.close()
    db.close()

ensure_giveaway_table()

class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="giveaway")
    async def giveaway(self, ctx: commands.Context):
        """Interactive giveaway setup with UI improvements"""
        embed = discord.Embed(
            title="🎉 Giveaway Setup",
            description="Click the button below to start creating a giveaway!",
            color=discord.Color.blurple()
        )
        view = View()
        start_button = Button(label="Start Giveaway", style=discord.ButtonStyle.green, emoji="🎉")
        view.add_item(start_button)

        async def start_callback(interaction: discord.Interaction):
            if interaction.user != ctx.author:
                return await interaction.response.send_message(
                    "⚠️ Only the command author can use this button.", ephemeral=True
                )

            await interaction.response.send_message(
                "Let's set up your giveaway! I'll ask a few questions in DM.", ephemeral=True
            )

            def check(m):
                return m.author == ctx.author and isinstance(m.channel, discord.DMChannel)

            try:
                await ctx.author.send("⏱ **Enter duration in minutes:**")
                duration_msg = await self.bot.wait_for("message", check=check, timeout=300)
                duration_minutes = int(duration_msg.content)

                await ctx.author.send("🏆 **Enter number of winners:**")
                winners_msg = await self.bot.wait_for("message", check=check, timeout=300)
                winners = int(winners_msg.content)

                await ctx.author.send("🎁 **Enter prize(s):**")
                prizes_msg = await self.bot.wait_for("message", check=check, timeout=300)
                prizes = prizes_msg.content

                await ctx.author.send("✉️ **Any extra message?** (Optional, type 'none' to skip)")
                extra_msg = await self.bot.wait_for("message", check=check, timeout=300)
                message = "" if extra_msg.content.lower() == "none" else extra_msg.content

                start_time = datetime.utcnow()
                end_time = start_time + timedelta(minutes=duration_minutes)

                db = get_db()
                cursor = db.cursor()
                cursor.execute(
                    "INSERT INTO giveaways (host_id, channel_id, duration_minutes, winners, prizes, message, start_time, end_time) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (ctx.author.id, ctx.channel.id, duration_minutes, winners, prizes, message, start_time, end_time)
                )
                db.commit()
                cursor.close()
                db.close()

                giveaway_embed = discord.Embed(
                    title="🎉 A New Giveaway Has Started! 🎉",
                    description=(
                        f"🎁 **Prize:** {prizes}\n"
                        f"⏱ **Duration:** {duration_minutes} minutes\n"
                        f"🏆 **Number of Winners:** {winners}\n\n"
                        f"{message if message else ''}"
                    ),
                    color=discord.Color.blurple()
                )
                giveaway_embed.set_footer(text=f"Hosted by {ctx.author}", icon_url=ctx.author.display_avatar.url)
                giveaway_embed.set_image(url="https://media.discordapp.net/attachments/1412722866134323270/1414656030914379837/bg.png?ex=68c05c98&is=68bf0b18&hm=d2e8f85ac9a70e0b387058ee1169707bb41b3f73a1b7aae095311ab1716ad197&=&format=webp&quality=lossless&width=1500&height=844")

                from discord import TextChannel
                giveaway_channel = self.bot.get_channel(config.GIVEAWAY_CHANNEL_ID)

                if isinstance(giveaway_channel, TextChannel):
                    giveaway_msg = await giveaway_channel.send(embed=giveaway_embed)
                    await giveaway_msg.add_reaction("🎉")
                else:
                    await ctx.send("⚠️ The giveaway channel is not a text channel or could not be found.")
                    return

                await ctx.message.delete()
                await ctx.author.send("✅ Giveaway created successfully!")

                await asyncio.sleep(duration_minutes * 60)

                updated_msg = await giveaway_channel.fetch_message(giveaway_msg.id)
                reaction = updated_msg.reactions[0]
                users = [u async for u in reaction.users() if not u.bot]

                if not users:
                    return await giveaway_channel.send("❌ Nobody entered the giveaway.")

                winners_list = random.sample(users, min(len(users), winners))
                winner_mentions = ", ".join(w.mention for w in winners_list)

                # End embed
                end_embed = discord.Embed(
                    title="🏆 Giveaway Ended!",
                    description=f"🎁 **Prize:** {prizes}\n📅 Hosted by {ctx.author.mention}",
                    color=discord.Color.gold()
                )
                await giveaway_channel.send(embed=end_embed)
                await giveaway_channel.send(f"🎉 Congratulations to the winner(s): {winner_mentions}!")

            except asyncio.TimeoutError:
                await ctx.author.send("⚠️ Giveaway setup timed out. Please try again.")

        start_button.callback = start_callback
        await ctx.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
