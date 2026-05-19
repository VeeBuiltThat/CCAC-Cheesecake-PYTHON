# sticky_messages.py
import discord
from discord.ext import commands
from datetime import datetime
import json
import os
import asyncio

STICKY_FILE = "sticky_messages.json"
STICKY_COOLDOWN = 10  # seconds

STICKY_TEMPLATES = {
    "trusted": {
        "title": "**TRUSTED GUIDELINES**",
        "description": (
            "Please remember when in <#1246266893925482641>\n\n"
            "<:macaronn:1244381480726171749> | SFW REQUESTS & IMAGES ONLY! "
            "To gain access to NSFW exchange, verify your 18+ status here: <@1420311570172346408>\n"
            "<:macaronn:1244381480726171749> | Please make sure to include a numerical budget (ex. $20-40USD, $60+USD). "
            "Include your desired style and reference images.\n"
            "<:macaronn:1244381480726171749> | Remember that the server minimum pricing is **__15USD__**. "
            "<:macaronn:1244381480726171749> | Please don't bump your buying posts! Artists will reach out from your initial post.\n"
            "<:macaronn:1244381480726171749> | Indicate the status of your buying post to avoid unwanted DMs.\n\n"
        ),
        "color": 0x00ff00
    },
    "buyer": {
        "title": "**BUYER GUIDE**",
        "description": (
            "Please remember when in <#1243567009564721243>\n\n"
            "<:macaronn:1244381480726171749> | SFW REQUESTS & IMAGES ONLY! "
            "To gain access to NSFW exchange, verify your 18+ status here: <@1420311570172346408>\n"
            "<:macaronn:1244381480726171749> | Please make sure to include a numerical budget (ex. $20-40USD, $60+USD). "
            "Include your desired style and reference images.\n"
            "<:macaronn:1244381480726171749> | Remember that the server minimum pricing is **__15USD__**. "
            "<:macaronn:1244381480726171749> | Please don't bump your buying posts! Artists will reach out from your initial post.\n"
            "<:macaronn:1244381480726171749> | Indicate the status of your buying post to avoid unwanted DMs.\n\n"
        ),
        "color": 0xf8dddd
    },
    "alt": {
        "title": "**OTHER-PAYMENT RULES**",
        "description": (
            "Please remember when in <#1244400051879546930>\n\n"
            "<:macaronn:1244381480726171749> | SFW REQUESTS & IMAGES ONLY! "
            "To gain access to NSFW exchange, verify your 18+ status here: <@1420311570172346408> \n"
            "<:macaronn:1244381480726171749> | Please make sure to include a numerical budget (ex. $20-40USD, $60+USD). "
            "Include your desired style and reference images.\n"
            "<:macaronn:1244381480726171749> | Remember that the server minimum pricing is **__15USD__**. "
            "<:macaronn:1244381480726171749> | Please don't bump your buying posts! Artists will reach out from your initial post.\n"
            "<:macaronn:1244381480726171749> | Indicate the status of your buying post to avoid unwanted DMs.\n\n"
        ),
        "color": 0xffa500
    },
    "nsfw": {
        "title": "**NSFW GUIDE**",
        "description": (
            "Please remember when in <#1242925169681502322>\n\n"
            "<:macaronn:1244381480726171749> | Please make sure to include a numerical budget (ex. $20-40USD, $60+USD). "
            "Include your desired style and reference images.\n"
            "<:macaronn:1244381480726171749> | Remember that the server minimum pricing is **__15USD__**. "
            "<:macaronn:1244381480726171749> | Please don't bump your buying posts! Artists will reach out from your initial post.\n"
            "<:macaronn:1244381480726171749> | Indicate the status of your buying post to avoid unwanted DMs.\n\n"
        ),
        "color": 0xff5555
    },
    "seller": {
        "title": "**SELLER GUIDE**",
        "description": (
            "<:Icon_cupcake:1244069853162242059> | Our server has a **__$15 MINIMUM__** for all members, artists, and buyers alike! That means your minimum price on all of your commission shas to be __$15__.\n"
            "<:Icon_cupcake:1244069853162242059> | Bundles can meet the $15 threshold (e.g., 3 headshots for $15). Bundles can be a maximum of 3 items for the minimum price ( $15 USD ) to have more items in a bundle the price must be higher\n"
            "<:Icon_cupcake:1244069853162242059> | Bases & on-base adopts are **EXEMPT** from the minimum.\n"
            "<:Icon_cupcake:1244069853162242059> | Prices **MUST** be displayed in the post.\n"
            "This ensures fair compensation and reduces scams. Inform staff through <@1420311570172346408> if someone tries to underpay.\n"
            "**This message is stickied to the bottom of the channel and is not directed at any member.**\n\n"
        ),
        "color": 0xf8dddd
    },
    "nsfwseller": {
        "title": "**NSFW SELLER GUIDE**",
        "description": (
            "<:Icon_cupcake:1244069853162242059> | Our server has a **__$15 MINIMUM__** for all members, artists, and buyers alike! That means your minimum price on all of your commission shas to be __$15__.\n"
            "<:Icon_cupcake:1244069853162242059> | Bundles can meet the $15 threshold (e.g., 3 headshots for $15). Bundles can be a maximum of 3 items for the minimum price ( $15 USD ) to have more items in a bundle the price must be higher\n"
            "<:Icon_cupcake:1244069853162242059> | Bases & on-base adopts are **EXEMPT** from the minimum.\n"
            "<:Icon_cupcake:1244069853162242059> | Prices **MUST** be displayed in the post.\n"
            "This ensures fair compensation and reduces scams. Inform staff through <@1420311570172346408> if someone tries to underpay.\n"
            "**This message is stickied to the bottom of the channel and is not directed at any member.**\n\n"
        ),
        "color": 0xff5555
    },
    "staff": {
        "title": "**Staff Availability**", 
        "description": (
            "<:Icon_cupcake:1244069853162242059> | Staff members are expected to uphold the community guidelines and ensure a safe environment for all members.\n"
            "<:Icon_cupcake:1244069853162242059> | Please monitor channels regularly and address any issues promptly.\n"
            "<:Icon_cupcake:1244069853162242059> | Remember to communicate clearly and respectfully with members.\n"
            "**If you would like to be pinged when our members need staff assistance, please react with <:Ban_Hammer:1244374720464551936> and you will gain the <@&1422222372471046154>**\n\n"
        ),
        "color": 0xff5555
    },
    "partner": {
        "title": "**Partnership requirements**", 
        "description": (
            "<:Icon_cupcake:1244069853162242059> | At least 1500 members\n"
            "<:Icon_cupcake:1244069853162242059> | Server must be at least **1 year old**\n"
            "<:Icon_cupcake:1244069853162242059> | Art focused community\n"
            "<:Icon_cupcake:1244069853162242059> | NSFW must be hidden behind verification\n"
            "<:Icon_cupcake:1244069853162242059> | Consistently active\n"
            "<:Icon_cupcake:1244069853162242059> | No AI Artwork\n"
            "**If you would like to apply for a partnership, please contact us through <@1420311570172346408>\n\n"
        ),
        "color": 0xffb6c1
    },
    "verify": {
        "title": "**Verification guide**", 
        "description": (
            "# Welcome to **Cheesecake Art Cafe** server!\n\n"
            "<@1310970252447711343> has sent you a verification message to access the server. Please make sure to read the message carefully and follow the instructions provided.\n"
            "When enterting the password you do not need to inlcude the `<>` brackets.\n"
            "> You are not supposed to see the previous messages in this chat. If you do, please inform a staff member through <@1420311570172346408> immediately as this could be a security issue.\n\n"
            "If you are unsure about the verification process, please read <#1431231498903752744> for more information.\n\n"
            "**If you are having issues with verification, please contact <@1420311570172346408> with the beggining message [TECH]\n\n"
        ),
        "color": 0xffb6c1
    },
    "social": {
        "title": "**Cheesecake Art Cafe - Social Media*", 
        "description": (
            "<:Icon_cupcake:1244069853162242059> | **[Instagram](https://www.instagram.com/cheesecakeartcafe/)**\n"
            "<:Icon_cupcake:1244069853162242059> | **[TikTok](https://www.tiktok.com/@cheesecake.art.cafe)**\n"
            "<:Icon_cupcake:1244069853162242059> | **[Twitch](https://www.twitch.tv/cheesecakeartcafe)**\n"
            "<:Icon_cupcake:1244069853162242059> | **[Carrd](https://ccac.carrd.co/)**\n"
            "<:Icon_cupcake:1244069853162242059> | **[Ko-Fi](https://ko-fi.com/cheesecakeartcafe#tier17171840750102)**\n\n"
        ),
        "color": 0xffb6c1
    },
    "dixie": {
        "title": "**Dixie Violations**", 
        "description": (
            "<:Icon_cupcake:1244069853162242059> | If the post does not violate any rules, make sure to press the button **cancel**\n"
            "<:Icon_cupcake:1244069853162242059> | If the post has a known violation, check the dropdown 'Choose an automated message', premade messages can be viewed **__[here](https://discord.com/channels/1240448660266029126/1338401271119347743/1420352932997628005)__**\n"
            "<:Icon_cupcake:1244069853162242059> | If the post does not meet any known violations, please select ''Custom Message'' button, and write your own response.\n\n"
            "<:Icon_cupcake:1244069853162242059> | With any technical issues, please ping <@766005564190359552> in <#1245431550942904341>\n"
            "**This message is stickied to the bottom of the channel and is not directed at any member.**\n\n"
        ),
        "color": 0xffb6c1
    }
}

AUTO_STICKY_CHANNELS = {
    "trusted": [1246266893925482641],
    "buyer": [1243567009564721243],
    "alt": [1244400051879546930],
    "nsfw": [1242925169681502322],
    "seller": [1244399296279740558, 1240456287473369170, 1243567743538561064, 1243567946605793353],
    "nsfwseller": [1242925123422523462],
    "staff": [1416097827465068776],
    "partner": [1244065547826630657],
    "verify": [1412710902880538624],
    "social": [1279660188697362504],
    "dixie": [1338401271119347743]
}

class StickyMessages(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}
        self.sticky_messages = self.load_data()

    # ---------- persistence ----------
    def load_data(self):
        if not os.path.exists(STICKY_FILE):
            return {}
        with open(STICKY_FILE, "r") as f:
            return json.load(f)

    def save_data(self):
        with open(STICKY_FILE, "w") as f:
            json.dump(self.sticky_messages, f)

    # ---------- core logic ----------
    async def send_sticky(self, channel, sticky_type):
        if not hasattr(channel, "send"):
            return

        now = asyncio.get_event_loop().time()
        last = self.cooldowns.get(str(channel.id), 0)

        if now - last < STICKY_COOLDOWN:
            return

        self.cooldowns[str(channel.id)] = now

        template = STICKY_TEMPLATES.get(sticky_type)
        if not template:
            return

        old_id = self.sticky_messages.get(str(channel.id))
        if old_id:
            try:
                old_msg = await channel.fetch_message(old_id)
                await old_msg.delete()
            except (discord.NotFound, discord.Forbidden):
                pass

        embed = discord.Embed(
            title=template["title"],
            description=template["description"],
            color=template["color"]
        )

        embed.set_footer(
            text="By Cheesecake",
            icon_url=channel.guild.icon.url if channel.guild and channel.guild.icon else None
        )

        msg = await channel.send(embed=embed)
        self.sticky_messages[str(channel.id)] = msg.id
        self.save_data()

    async def remove_sticky(self, channel):
        if not hasattr(channel, "send"):
            return

        old_id = self.sticky_messages.get(str(channel.id))
        if not old_id:
            return

        try:
            msg = await channel.fetch_message(old_id)
            await msg.delete()
        except (discord.NotFound, discord.Forbidden):
            pass

        self.sticky_messages.pop(str(channel.id), None)
        self.save_data()

    # ---------- listeners ----------
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot:
            return

        for sticky_type, channels in AUTO_STICKY_CHANNELS.items():
            if message.channel.id in channels:
                await self.send_sticky(message.channel, sticky_type)
                break

    # ---------- commands ----------

    @commands.command(name="trustedstick")
    async def trusted_stick(self, ctx):
        await self.send_sticky(ctx.channel, "trusted")

    @commands.command(name="trustedremove")
    async def trusted_remove(self, ctx):
        await self.remove_sticky(ctx.channel)

    @commands.command(name="buyerstick")
    async def buyer_stick(self, ctx):
        await self.send_sticky(ctx.channel, "buyer")

    @commands.command(name="buyerremove")
    async def buyer_remove(self, ctx):
        await self.remove_sticky(ctx.channel)

    @commands.command(name="altstick")
    async def alt_stick(self, ctx):
        await self.send_sticky(ctx.channel, "alt")

    @commands.command(name="altremove")
    async def alt_remove(self, ctx):
        await self.remove_sticky(ctx.channel)

    @commands.command(name="nsfwstick")
    async def nsfw_stick(self, ctx):
        await self.send_sticky(ctx.channel, "nsfw")

    @commands.command(name="nsfwremove")
    async def nsfw_remove(self, ctx):
        await self.remove_sticky(ctx.channel)

    @commands.command(name="sellerstick")
    async def seller_stick(self, ctx):
        await self.send_sticky(ctx.channel, "seller")

    @commands.command(name="sellerremove")
    async def seller_remove(self, ctx):
        await self.remove_sticky(ctx.channel)

    @commands.command(name="nsfwsellerstick")
    async def nsfwseller_stick(self, ctx):
        await self.send_sticky(ctx.channel, "nsfwseller")

    @commands.command(name="nsfwsellerremove")
    async def nsfwseller_remove(self, ctx):
        await self.remove_sticky(ctx.channel)

    @commands.command(name="staffstick")
    async def staff_stick(self, ctx):
        await self.send_sticky(ctx.channel, "staff")

    @commands.command(name="staffremove")
    async def staff_remove(self, ctx):
        await self.remove_sticky(ctx.channel)

    @commands.command(name="partnerstick")
    async def partner_stick(self, ctx):
        await self.send_sticky(ctx.channel, "partner")

    @commands.command(name="partnerremove")
    async def partner_remove(self, ctx):
        await self.remove_sticky(ctx.channel)

    @commands.command(name="verifystick")
    async def verify_stick(self, ctx):
        await self.send_sticky(ctx.channel, "verify")

    @commands.command(name="verifyremove")
    async def verify_remove(self, ctx):
        await self.remove_sticky(ctx.channel)

    @commands.command(name="socialstick")
    async def social_stick(self, ctx):
        await self.send_sticky(ctx.channel, "social")

    @commands.command(name="socialremove")
    async def social_remove(self, ctx):
        await self.remove_sticky(ctx.channel)

    @commands.command(name="dixiestick")
    async def dixie_stick(self, ctx):
        await self.send_sticky(ctx.channel, "dixie")

    @commands.command(name="dixieremove")
    async def dixie_remove(self, ctx):
        await self.remove_sticky(ctx.channel)



async def setup(bot):
    await bot.add_cog(StickyMessages(bot))
