import discord
from discord.ext import commands
from . import config
ALLOWED_LOVE_REACTOR_CHANNELS = config.ALLOWED_LOVE_REACTOR_CHANNELS

class LoveReactor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return  

        if message.channel.id in ALLOWED_LOVE_REACTOR_CHANNELS:
            try:
                await message.add_reaction("💌")
            except discord.Forbidden:
                pass  
            except discord.HTTPException:
                pass 

async def setup(bot):
    await bot.add_cog(LoveReactor(bot))
