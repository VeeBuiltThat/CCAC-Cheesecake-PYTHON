import discord
import random
import pymysql
from discord.ext import commands
from . import config
ALLOWED_CHANNELS = config.ALLOWED_CHANNELS

def get_db():
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        autocommit=True
    )

def ensure_trigger_words_table():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trigger_words (
            id INT AUTO_INCREMENT PRIMARY KEY,
            trigger_text TEXT NOT NULL,
            response_text TEXT NOT NULL
        )
    """)
    db.commit()
    cursor.close()
    db.close()

def fetch_trigger_responses():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT trigger_text, response_text FROM trigger_words")
    rows = cursor.fetchall() or []
    cursor.close()
    db.close()
    return rows

def add_trigger(trigger_text, response_text):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "INSERT INTO trigger_words (trigger_text, response_text) VALUES (%s, %s)",
        (trigger_text, response_text)
    )
    db.commit()
    cursor.close()
    db.close()

def remove_trigger(trigger_text):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM trigger_words WHERE trigger_text=%s", (trigger_text,))
    db.commit()
    cursor.close()
    db.close()


ensure_trigger_words_table()

class ResponseHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        ensure_trigger_words_table()

    @staticmethod
    def get_response(user_input: str):
        lowered = user_input.lower()
        if not lowered.strip():
            return ''

        for trigger_text, response_text in fetch_trigger_responses():
            if not trigger_text or not response_text: 
                continue
            if trigger_text.lower() in lowered:
                return response_text

        if '$command_list' in lowered:
            return (
                "### - Informal\n"
                "how do i post images / why cant i post images? / level 15 / lvl 15\n"
                "how do i gain access to the vc stream? / how do i get access to the vc stream?\n"
                "what is a kulfi member?\n"
                "how can i become a trusted member? / how can i become a trusted seller? / how can i become a trusted buyer\n"
                "### - Cheesecakes greeting\n"
                "how are you / how's it going\n"
                "bye, cheesecake / goodbye, cheesecake / see you, cheesecake\n"
                "hello cheesecake / hey cheesecake / cheesecake, come say hi\n"
                "look cheesecake, a new member! / welcome to the server! / cheesecake, come meet your new friend\n"
                "### - Random things that cheesecake says\n"
                "hate it here\n"
                "i love you, cheesecake / i love you cheesecake / ily cheesecake\n"
                "queen shit\n"
                "tell me a joke, cheesecake\n"
                "cheesecake, have you ever seen a horror movie?\n"
                "cmon, say sorry / cheesecake, apologize / cheesecake, you have to apologize, cmon.\n"
                "i swear sometimes i hear her\n"
                "needy cheesecake\n"
                "<:Cheesecake_BigOlEyes:1243938784945639525>\n"
                "SCREAMS / screams / screaming\n"
                "Bri / bri / Bri?\n"
                "### - In case Cheesecake goes crazy\n"
                "eivroit / cheesecake is being silly! / cheesecake is crazy!"
            )

        elif '$staff command list' in lowered:
            return (
                "# **MODERATION SYSTEM**\n"
                "**__Warning System __**\n"
                "- **To warn a user:** `$warn <user> <reason>`\n"
                "- **To remove the warning:** `$removewarn <user> <reason>`\n"
                "- **To kick-out a user:** `$kick <user> <reason>`\n"
                "- **To ban a user:** `$ban <user> <reason>`\n"
                "- **To un-ban a user:** `$unban <user> <reason>`\n"
                "*Only mods and above can use this command*"
            )

        greetings = {
            "how are you, cheesecake": "Good, thanks!",
            "how's it going, cheesecake": "Good, thanks!",
            "bye cheesecake": "See you!",
            "goodbye, cheesecake": "See you!",
            "see you, cheesecake": "See you!",
            "hello cheesecake": "Yo!",
            "hey cheesecake": "Yo!",
            "cheesecake, come say hi": "Yo!"
        }
        for phrase, response in greetings.items():
            if phrase in lowered:
                return response

        info_responses = {
            "how do i post pictures?": "To post images you need to get level 15!",
            "how do i post images": "To post images you need to get level 15!",
            "why cant i post images?": "To post images you need to get level 15!",
            "level 15": "To post images you need to get level 15!",
            "lvl 15": "To post images you need to get level 15!",
            "how do i gain access to the vc stream?": "To get access in vc stream, you need level 15!",
            "how do i get access to the vc stream?": "To get access in vc stream, you need level 15!",
            "what is a kulfi member?": "They are our ko-fi supporters! You can also become one, all the information is in this channel <#1246161217773633556>",
            "how can i become a trusted member?": "Hey there, friend! To become a trusted member you need to go to <#1243586232282382377> and apply. Make sure to read the rules though <:Cheesecake_Love:1243565944090136709>",
            "how can i become a trusted seller?": "Hey there, friend! To become a trusted member you need to go to <#1243586232282382377> and apply. Make sure to read the rules though <:Cheesecake_Love:1243565944090136709>",
            "how can i become a trusted buyer": "Hey there, friend! To become a trusted member you need to go to <#1243586232282382377> and apply. Make sure to read the rules though <:Cheesecake_Love:1243565944090136709>",
            "emergency commissions": "DM <@1420311570172346408> to apply for emergency commissions!"
        }
        
        for phrase, response in info_responses.items():
            if phrase in lowered:
                return response

        fun_responses = {
            "meow": "meow",
            "pastel de queso": "CAKE OF CHEESE?!?!",
            "BRI": "Te amamos, bri <3",
            "bri": "Te amamos, bri <3",
            " Bri? ": "Te amamos, bri <3",
            "cheesecake is just very needy": "NO I AM NOT",
            "needy cheesecake": "NO I AM NOT",
            "screams": "AAAAAHHHHHHH",
            "SCREAMS": "AAAAAHHHHHHH",
            "screaming": "AAAAAHHHHHHH",
            "i swear sometimes i hear her": "Give code. :index_pointing_at_the_viewer:",
            "cheesecake_bigoleyes": "<:Cheesecake_BigOlEyes:1243938784945639525>"
        }
        for phrase, response in fun_responses.items():
            if phrase in lowered:
                return response

        multi_responses = [
            (['look cheesecake, a new member!', 'welcome to the server!', 'cheesecake, come meet your new friend'], [
                "Greetings, best baker cheesecake says hello!",
                "HII, I am so happy to see you here",
                "Yo, hope you enjoy your stay here",
                "OMG, OMG ANOTHER FRIEND, HELLO!!",
                "A new member?! Welcome to the café!",
                "oh, a new person ! come in !"
            ]),
            (['cmon, say sorry', 'cheesecake, apologize', 'cheesecake, you have to apologize, cmon.'], [
                "No.", "I don't wanna", "...", "I'm sorry...", "I'm sorry, I didn't mean that", "Make me."
            ]),
            (['i would die for you, cheesecake...'], [
                'I would burn the world for you...',
                'I pine for you',
                'Aww <3 I love you too',
                'I would take a bullet for you',
                'I would make a 4-story cake for you',
                'I would become your personal chef',
            ])
        ]
        for triggers, responses in multi_responses:
            if any(trigger in lowered for trigger in triggers):
                return random.choice(responses)

        return ''

    @commands.command(name="newres")
    @commands.has_permissions(manage_guild=True)
    async def add_new_response(self, ctx, *, args: str):
        if '|' not in args:
            await ctx.send("❌ Please use the format: `trigger text | response text`")
            return
        trigger_text, response_text = map(str.strip, args.split('|', 1))
        add_trigger(trigger_text, response_text)
        embed = discord.Embed(
            title="✅ New Trigger Added",
            description=f"**Trigger:** `{trigger_text}`\n**Response:** {response_text}",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="remove")
    @commands.has_permissions(manage_guild=True)
    async def remove_response(self, ctx, *, trigger_text: str):
        remove_trigger(trigger_text)
        embed = discord.Embed(
            title="🗑 Trigger Removed",
            description=f"All responses for **`{trigger_text}`** have been removed from the database.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ResponseHandler(bot))

