import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
import json
import atexit
from typing import Optional
import asyncio
from pathlib import Path

try:
    import msvcrt  # type: ignore
except ImportError:
    msvcrt = None

try:
    import fcntl  # type: ignore
except ImportError:
    fcntl = None

from cogs.responsehandler import ResponseHandler, ALLOWED_CHANNELS

load_dotenv()

intents = discord.Intents.default()
intents.members = True
intents.guilds = True
intents.reactions = True
intents = discord.Intents.all()

HELP_DESCRIPTIONS = {
    "help": "Open the help menu or show details for a specific command/category.",
    "cc": "Send a copied message through the bot.",
    "absence": "Mark yourself as absent so staff are notified and your leave is tracked.",
    "removeabsence": "Clear your absence status and restore normal staff notifications.",
    "addbday": "Save your birthday in the shared birthday list.",
    "removebday": "Remove a saved birthday entry by user ID.",
    "bdaylist": "Show the stored birthday list.",
    "reaction": "Link a reaction on a message to a server role.",
    "giveaway": "Start the guided giveaway setup flow.",
    "newres": "Add a new trigger and response pair for the auto-response system.",
    "remove": "Remove an auto-response trigger from the database.",
    "newevent": "Create a new event channel in the event category.",
    "info": "Post an event information embed in the current channel.",
    "start": "Enable hidden voting reactions for image posts in the current event channel.",
    "stop": "Disable voting reactions in the current event channel.",
    "vote": "Show the top voter for a selected event channel.",
    "addvote": "Manually add a vote for a user to an event entry.",
    "post_emergency_rules": "Post the emergency commissions rules panel with the apply button.",
    "reject_emergency": "Reject an emergency commission application manually.",
    "cleanup_emergency_posts": "Delete expired emergency commission posts and clean the log.",
    "trustedstick": "Post the trusted-member sticky guide in this channel.",
    "trustedremove": "Remove the trusted-member sticky guide from this channel.",
    "buyerstick": "Post the buyer guide sticky in this channel.",
    "buyerremove": "Remove the buyer guide sticky from this channel.",
    "altstick": "Post the alternate account rules sticky in this channel.",
    "altremove": "Remove the alternate account sticky from this channel.",
    "nsfwstick": "Post the NSFW guide sticky in this channel.",
    "nsfwremove": "Remove the NSFW guide sticky from this channel.",
    "sellerstick": "Post the seller guide sticky in this channel.",
    "sellerremove": "Remove the seller guide sticky from this channel.",
    "nsfwsellerstick": "Post the NSFW seller guide sticky in this channel.",
    "nsfwsellerremove": "Remove the NSFW seller guide sticky from this channel.",
    "staffstick": "Post the staff guide sticky in this channel.",
    "staffremove": "Remove the staff guide sticky from this channel.",
    "partnerstick": "Post the partner guide sticky in this channel.",
    "partnerremove": "Remove the partner guide sticky from this channel.",
    "verifystick": "Post the verification help sticky in this channel.",
    "verifyremove": "Remove the verification sticky from this channel.",
    "socialstick": "Post the social links sticky in this channel.",
    "socialremove": "Remove the social links sticky from this channel.",
    "dixiestick": "Post the Dixie violations staff sticky in this channel.",
    "dixieremove": "Remove the Dixie violations sticky from this channel.",
}

HELP_CATEGORY_DESCRIPTIONS = {
    "Absence": "Staff leave tracking and return management.",
    "Birthday": "Birthday reminders and staff birthday admin tools.",
    "EventCog": "Event channel creation and voting controls.",
    "Giveaway": "Giveaway setup and hosting tools.",
    "ResponseHandler": "Auto-response trigger management.",
    "StickyMessages": "Sticky guide posting and removal commands.",
    "Emergency": "Emergency commissions workflow and moderation tools.",
    "General": "General bot utilities.",
}

LOCK_FILE_PATH = Path(".cheesecake-main.lock")
_LOCK_FILE_HANDLE = None


def _claim_runtime_lock() -> None:
    global _LOCK_FILE_HANDLE
    lock_handle = open(LOCK_FILE_PATH, "a+")

    try:
        lock_handle.seek(0)
        if os.name == "nt":
            if msvcrt is None:
                raise RuntimeError("Windows file locking is unavailable on this runtime.")
            msvcrt.locking(lock_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            if fcntl is None:
                raise RuntimeError("POSIX file locking is unavailable on this runtime.")
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        lock_handle.close()
        raise RuntimeError("Another Cheesecake main.py process is already running.") from exc

    _LOCK_FILE_HANDLE = lock_handle


def _release_runtime_lock() -> None:
    global _LOCK_FILE_HANDLE
    if _LOCK_FILE_HANDLE is None:
        return

    try:
        _LOCK_FILE_HANDLE.seek(0)
        if os.name == "nt":
            if msvcrt is not None:
                msvcrt.locking(_LOCK_FILE_HANDLE.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            if fcntl is not None:
                fcntl.flock(_LOCK_FILE_HANDLE.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    finally:
        _LOCK_FILE_HANDLE.close()
        _LOCK_FILE_HANDLE = None


class CheesecakeHelpCommand(commands.HelpCommand):
    MAX_EMBED_DESCRIPTION = 4000
    MAX_FIELDS_PER_EMBED = 25
    MAX_FIELD_VALUE = 1024

    def __init__(self):
        super().__init__(
            command_attrs={
                "help": "Show the help menu.",
            }
        )

    def _prefix(self) -> str:
        return self.context.clean_prefix if self.context else "$"

    def _build_embed(self, title: str, description: str) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            color=discord.Color(0xFF69B4),
        )
        embed.set_footer(
            text=(
                f"Use {self._prefix()}help <command> for details | "
                f"Use {self._prefix()}help <category> for command groups"
            )
        )
        return embed

    def _describe_command(self, command: commands.Command) -> str:
        return (
            HELP_DESCRIPTIONS.get(command.qualified_name)
            or HELP_DESCRIPTIONS.get(command.name)
            or command.help
            or command.short_doc
            or "No description available."
        )

    def _chunk_lines(self, lines: list[str], limit: int | None = None) -> list[str]:
        chunk_limit = limit or self.MAX_EMBED_DESCRIPTION
        chunks: list[str] = []
        current: list[str] = []
        current_length = 0

        for line in lines:
            line_length = len(line) + (1 if current else 0)
            if current and current_length + line_length > chunk_limit:
                chunks.append("\n".join(current))
                current = [line]
                current_length = len(line)
            else:
                current.append(line)
                current_length += line_length

        if current:
            chunks.append("\n".join(current))

        return chunks or ["No commands."]

    async def _send_paginated_descriptions(self, title: str, descriptions: list[str]) -> None:
        total = len(descriptions)
        for index, description in enumerate(descriptions, start=1):
            embed = self._build_embed(title=title, description=description)
            if total > 1:
                embed.set_author(name=f"Page {index}/{total}")
            await self.get_destination().send(embed=embed)

    async def _send_embeds(self, embeds: list[discord.Embed]) -> None:
        total = len(embeds)
        for index, embed in enumerate(embeds, start=1):
            if total > 1:
                embed.set_author(name=f"Page {index}/{total}")
            await self.get_destination().send(embed=embed)

    def _format_command_line(self, command: commands.Command) -> str:
        short = self._describe_command(command)
        return f"{self._prefix()}{command.qualified_name} - {short}"

    async def send_bot_help(self, mapping):
        filtered_commands = await self.filter_commands(self.context.bot.commands, sort=True)
        categories: dict[str, list[commands.Command]] = {}

        for command in filtered_commands:
            cog_name = command.cog.qualified_name if command.cog else "General"
            categories.setdefault(cog_name, []).append(command)

        intro = (
            "Here are the commands you can use in this channel. "
            "Commands shown are filtered by your permissions."
        )
        embeds: list[discord.Embed] = []
        embed = self._build_embed(
            title="Cheesecake Help Menu",
            description=intro,
        )

        for category in sorted(categories):
            commands_in_category = sorted(categories[category], key=lambda c: c.qualified_name)
            preview = "\n".join(self._format_command_line(cmd) for cmd in commands_in_category)
            category_description = HELP_CATEGORY_DESCRIPTIONS.get(category)
            if category_description:
                preview = f"{category_description}\n\n{preview}"
            field_chunks = self._chunk_lines(preview.split("\n"), self.MAX_FIELD_VALUE)

            for chunk_index, chunk in enumerate(field_chunks, start=1):
                field_name = category if chunk_index == 1 else f"{category} (cont.)"
                if len(embed.fields) >= self.MAX_FIELDS_PER_EMBED:
                    embeds.append(embed)
                    embed = self._build_embed(title="Cheesecake Help Menu", description=intro)
                embed.add_field(name=field_name, value=chunk or "No commands.", inline=False)

        embeds.append(embed)
        await self._send_embeds(embeds)

    async def send_cog_help(self, cog):
        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        if not filtered:
            await self.get_destination().send("No commands are available in this category.")
            return

        lines = [self._format_command_line(command) for command in filtered]
        description_lines: list[str] = []
        category_description = HELP_CATEGORY_DESCRIPTIONS.get(cog.qualified_name)
        if category_description:
            description_lines.extend([category_description, ""])
        description_lines.extend(lines)

        descriptions = self._chunk_lines(description_lines)
        await self._send_paginated_descriptions(
            title=f"Category: {cog.qualified_name}",
            descriptions=descriptions,
        )

    async def send_group_help(self, group):
        embed = self._build_embed(
            title=f"Group: {group.qualified_name}",
            description=group.help or group.short_doc or "No description available.",
        )
        embed.add_field(
            name="Usage",
            value=f"{self._prefix()}{group.qualified_name} {group.signature}".strip(),
            inline=False,
        )

        subcommands = await self.filter_commands(group.commands, sort=True)
        if subcommands:
            embed.add_field(
                name="Subcommands",
                value="\n".join(self._format_command_line(cmd) for cmd in subcommands),
                inline=False,
            )

        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        embed = self._build_embed(
            title=f"Command: {command.qualified_name}",
            description=self._describe_command(command),
        )
        embed.add_field(
            name="Usage",
            value=f"{self._prefix()}{command.qualified_name} {command.signature}".strip(),
            inline=False,
        )

        if command.cog:
            embed.add_field(name="Category", value=command.cog.qualified_name, inline=False)

        if command.aliases:
            embed.add_field(name="Aliases", value=", ".join(command.aliases), inline=False)

        await self.get_destination().send(embed=embed)


bot = commands.Bot(command_prefix='$', intents=intents, help_command=CheesecakeHelpCommand())
atexit.register(_release_runtime_lock)

# Tracks recent Discord message IDs that were already handled in this process.
_PROCESSED_MESSAGE_IDS: set[int] = set()


def _claim_message_once(message_id: Optional[int]) -> bool:
    if message_id is None:
        return True
    if message_id in _PROCESSED_MESSAGE_IDS:
        return False
    _PROCESSED_MESSAGE_IDS.add(message_id)
    if len(_PROCESSED_MESSAGE_IDS) > 10000:
        # Keep memory bounded while still covering recent duplicate deliveries.
        _PROCESSED_MESSAGE_IDS.clear()
    return True

JR_MODS = "1334289756539846656"
MODS = "1243559774847766619"
ADMINS = "1243929060145631262"
OWNERS = "1240455108047671406"
BOT_MANAGER = "766005564190359552"

DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
if DISCORD_TOKEN is None:
    raise ValueError('Bot token not found. Please ensure the token variable is set correctly.')

# --- DO NOT REMOVE: Used for mental health support responses ---
MENTAL_HEALTH_TRIGGERS = ["kms", "ankill myselfxious", "suicidal", "self harm", "self harming"]

MENTAL_HEALTH_MESSAGE = (
    "**Mental Health Resources**\n"
    "If you're struggling, please know you're not alone. Here are some resources that might help:\n"
    "- [Mental Health America](<https://mhanational.org/get-involved/contact-us>)\n"
    "- [Crisis Text Line](<https://www.crisistextline.org/>) (Text HOME to 741741)\n"
    "- [National Suicide Prevention Lifeline](<https://988lifeline.org/>) (Call 988)\n"
    "- [Find a Therapist](<https://www.psychologytoday.com/us/therapists>)\n"
    "If you need someone to talk to, please reach out to a trusted friend, family member, or a professional. 💚"
)

@bot.event
async def on_ready():
    print(f"Yo, It's me, {bot.user}")

    for filename in os.listdir("./cogs"):
        if filename.endswith(".py"):
            try:
                await bot.load_extension(f"cogs.{filename[:-3]}")
                print(f"✅ Loaded cog: {filename}")
            except Exception as e:
                print(f"❌ Failed to load cog {filename}: {e}")

            

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if not _claim_message_once(getattr(message, "id", None)):
        return

    if any(word in message.content.lower() for word in MENTAL_HEALTH_TRIGGERS):
        await message.channel.send(f"{message.author.mention} {MENTAL_HEALTH_MESSAGE}")

    await bot.process_commands(message)

    # Do not run auto-response matching for command messages.
    if message.content.strip().startswith(str(bot.command_prefix)):
        return

    if message.channel.id in ALLOWED_CHANNELS:
        response = ResponseHandler.get_response(message.content)
        if response:
            await message.channel.send(response)

@bot.command(name='cc')
async def copy_message(ctx, *, message):
    """
    Copies and sends the provided message with a typing indicator
    Usage: $cc <message>
    """
    if ctx.channel.id:
        return
        
    await ctx.message.delete() 
    async with ctx.typing():
        await asyncio.sleep(1)
        await ctx.send(message)

@bot.event
async def on_member_join(member):
    welcome_channel_id = 1240449334642741308
    welcome_channel = member.guild.get_channel(welcome_channel_id)
    if welcome_channel is None:
        print("Welcome channel not found.")
        return

    member_count = member.guild.member_count

    embed = discord.Embed(
        title="Welcome to Cheesecake Art Café!",
        description=(
            f"Hey {member.mention}, welcome to **Cheesecake Art Café**! You are the {member_count} customer. Enjoy your stay!\n\n"
            "<a:aPink_Arrow:1244331554872758343> Make sure to read the rules of the server: <#1240449206297300992>\n"
            "<a:aPink_Arrow:1244331554872758343> After you've verified, check out <#1243567504542924852> & grab roles here: <#1244611036619735113>!\n"
            "<a:aPink_Arrow:1244331554872758343> If you're having trouble verifying, please contact our bot <@1310970252447711343> <#1414519063035514900>."
        ),
        color=discord.Color(0xFF69B4) 
    )
    avatar_url = member.display_avatar.url if hasattr(member, "display_avatar") else member.avatar.url if member.avatar else member.default_avatar.url
    embed.set_image(url="https://images-ext-1.discordapp.net/external/SjUljO-GGzBmtt42fK6p1k471y2-38DCo6j2KslSW3k/https/i.imgur.com/9N5YWS2.png?format=webp&quality=lossless&width=1406&height=375")
    embed.set_thumbnail(url=avatar_url)
    await welcome_channel.send(content=member.mention, embed=embed)

try:
    _claim_runtime_lock()
    bot.run(DISCORD_TOKEN)
except discord.errors.LoginFailure as e:
    print(f"Failed to log in: {e}")
except Exception as e:
    print(f"An error occurred: {e}")