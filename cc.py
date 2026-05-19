import discord
import os
import random
import asyncio
import logging
from discord.ext import tasks
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
load_dotenv()

AUTHORIZED_USER = 766005564190359552

STATUSES = [
    "Cooking up pastries",
    "HIII",
    "Attempting not to cry",
    "Need Help? Contact Mousse The Mouse",
    "I love Dixie so much <3",
]

active_channel_id: int | None = None

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.dm_messages = True

client = discord.Client(intents=intents)


# ---------------- Typing Simulation ----------------

def calculate_typing_duration(text: str) -> float:
    cpm = 190.0
    base = (len(text) / cpm) * 60.0
    random_factor = random.uniform(0.5, 2.0)
    total = base * random_factor
    return max(1.0, min(total, 12.0))


async def simulate_typing(channel: discord.TextChannel, duration: float):
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < duration:
        async with channel.typing():
            remaining = duration - (asyncio.get_event_loop().time() - start)
            await asyncio.sleep(min(8.0, remaining))


# ---------------- Realistic Messaging ----------------

def split_message(text: str, limit: int = 1800) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks = []
    while len(text) > limit:
        split_at = text[:limit].rfind(" ")
        if split_at == -1:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:]
    if text:
        chunks.append(text)
    return chunks


async def send_realistic_message(channel: discord.TextChannel, content: str):
    chunks = split_message(content)
    for i, chunk in enumerate(chunks):
        duration = calculate_typing_duration(chunk)
        await simulate_typing(channel, duration)
        await channel.send(chunk)
        if i < len(chunks) - 1:
            await asyncio.sleep(random.uniform(0.5, 2.0))


async def send_realistic_reply(channel: discord.TextChannel, message_id: int, content: str):
    duration = calculate_typing_duration(content)
    await simulate_typing(channel, duration)
    try:
        msg = await channel.fetch_message(message_id)
        await msg.reply(content)
    except discord.NotFound:
        logging.error(f"Message {message_id} not found.")


async def send_realistic_attachment(channel: discord.TextChannel, url: str):
    await asyncio.sleep(random.uniform(1.0, 3.0))
    await simulate_typing(channel, 2.0)
    await channel.send(url)


# ---------------- Message Handler ----------------

@client.event
async def on_message(message: discord.Message):
    global active_channel_id

    if message.author.bot or message.author.id != AUTHORIZED_USER:
        return

    content = message.content.strip()

    if content.startswith("!start "):
        args = content.split(" ")
        if len(args) != 2:
            await message.channel.send("Usage: !start <channel_id>")
            return
        active_channel_id = int(args[1])
        await message.channel.send("Forwarding activated.")
        return

    if content.startswith("!change "):
        args = content.split(" ")
        if len(args) != 2:
            await message.channel.send("Usage: !change <channel_id>")
            return
        active_channel_id = int(args[1])
        await message.channel.send("Forwarding channel changed.")
        return

    if content.startswith("!reply "):
        if active_channel_id is None:
            return
        parts = content.split(" ", 2)
        if len(parts) < 3:
            await message.channel.send("Usage: !reply <message_id> <text>")
            return
        message_id = int(parts[1])
        reply_text = parts[2]
        channel = client.get_channel(active_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        await send_realistic_reply(channel, message_id, reply_text)
        return

    if active_channel_id is None or content.startswith("!"):
        return

    # Don't forward if you're already talking in the active channel
    if message.channel.id == active_channel_id:
        return

    channel = client.get_channel(active_channel_id)
    if not isinstance(channel, discord.TextChannel):
        return

    if content:
        await send_realistic_message(channel, content)

    for attachment in message.attachments:
        await send_realistic_attachment(channel, attachment.url)


# ---------------- Status Updater ----------------

@tasks.loop(minutes=5)
async def status_updater():
    status = random.choice(STATUSES)
    await client.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=status,
        ),
    )


@client.event
async def on_ready():
    logging.info(f"Logged in as {client.user}")
    status_updater.start()


# ---------------- Entry Point ----------------

# Use a dedicated token for this relay utility so it cannot accidentally
# run alongside the main bot on the same Discord application.
token = os.getenv("CC_DISCORD_TOKEN")
if not token:
    raise RuntimeError("Set CC_DISCORD_TOKEN for cc.py; do not reuse the main bot token here")

client.run(token)
