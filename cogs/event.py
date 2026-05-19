import discord
from discord.ext import commands
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
from typing import Optional
import pymysql
from . import config

# Configuration constants
EVENTS_CATEGORY_ID = 1412722642321932298
VOTE_LOG_CHANNEL_ID = 1459105274332844053   # where vote logs are posted
COMMANDS_CHANNEL_ID = 1431691032516366337   # where $vote and $addvote must be used
VOTING_EMOJI_ID: Optional[int] = 1244381480726171749
VOTING_EMOJI_NAME = "Icon_macaron"
VOTING_EMOJI_STR = f"<:{VOTING_EMOJI_NAME}:{VOTING_EMOJI_ID}>"
VOTING_PARTIAL = discord.PartialEmoji(name=VOTING_EMOJI_NAME, id=VOTING_EMOJI_ID)
MIN_JOIN_DAYS = 30


def get_db():
    return pymysql.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
        database=config.DB_NAME,
        autocommit=True
    )


def ensure_event_tables():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_channels (
            channel_id BIGINT PRIMARY KEY,
            name VARCHAR(100),
            created_by BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_votes (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            guild_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            message_id BIGINT NOT NULL,
            voter_id BIGINT NOT NULL,
            voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    try:
        cursor.execute("""
            DELETE e1 FROM event_votes e1
            INNER JOIN event_votes e2
            WHERE e1.channel_id = e2.channel_id AND e1.voter_id = e2.voter_id AND e1.id < e2.id
        """)
    except Exception:
        pass
    try:
        cursor.execute("ALTER TABLE event_votes ADD UNIQUE KEY uniq_channel_voter (channel_id, voter_id)")
    except Exception:
        pass
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_voting_channels (
            channel_id BIGINT PRIMARY KEY,
            started_by BIGINT,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS processed_event_commands (
            message_id BIGINT PRIMARY KEY,
            command_name VARCHAR(100) NOT NULL,
            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.close()
    db.close()

ensure_event_tables()


def is_image_message(message: discord.Message) -> bool:
    for a in message.attachments:
        if (a.content_type and a.content_type.startswith("image")) or a.filename.lower().endswith(
            (".png", ".jpg", ".jpeg", ".gif", ".webp")
        ):
            return True
    for e in message.embeds:
        if e.type == "image" or getattr(e, "image", None):
            return True
    return False


class EventCog(commands.Cog):
    """
    Event channels & image voting cog.

    Commands:
    - $newevent <name>               — create a text channel under EVENTS_CATEGORY_ID
    - $info <message>                — send an informational embed with server icon
    - $start                         — enable voting in the current channel
    - $stop                          — disable voting in the current channel
    - $vote                          — show top voter(s); only usable in VOTE_LOG_CHANNEL_ID
    - $addvote <user_id> <message_id> — manually add a vote (admin only, in log channel)

    Voting behavior:
    - Bot adds Icon_macaron to every new image post in active channels.
    - When a user reacts, their reaction is immediately removed (count stays hidden at 1).
    - Vote is recorded in DB and logged to VOTE_LOG_CHANNEL_ID.
    - Members who joined < MIN_JOIN_DAYS ago are rejected silently via DM.
    - Each user can only vote once per channel.
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_channels: set[int] = set()
        self.votes: defaultdict[int, Counter] = defaultdict(Counter)
        self._seen_command_messages: set[int] = set()
        # Tracks (channel_id, voter_id) pairs currently being processed to prevent race double-fires
        self._in_flight: set[tuple[int, int]] = set()

        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("SELECT channel_id FROM active_voting_channels")
            for (cid,) in cursor.fetchall() or []:
                self.active_channels.add(cid)
            cursor.execute(
                "SELECT channel_id, voter_id, COUNT(*) FROM event_votes GROUP BY channel_id, voter_id"
            )
            for channel_id, voter_id, cnt in cursor.fetchall() or []:
                self.votes[channel_id][voter_id] = cnt
            cursor.close()
            db.close()
        except Exception:
            pass

    def _claim_command_once(self, ctx: commands.Context, command_name: str) -> bool:
        message_id = getattr(getattr(ctx, "message", None), "id", None)
        if message_id is None:
            return True

        if message_id in self._seen_command_messages:
            return False

        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                "INSERT IGNORE INTO processed_event_commands (message_id, command_name) VALUES (%s, %s)",
                (message_id, command_name),
            )
            inserted = cursor.rowcount == 1
            cursor.close()
            db.close()
            if not inserted:
                return False
        except Exception:
            if message_id in self._seen_command_messages:
                return False

        self._seen_command_messages.add(message_id)
        if len(self._seen_command_messages) > 10000:
            self._seen_command_messages.clear()
        return True

    # -------------------------
    # Internal vote recorder
    # -------------------------
    async def _record_vote(
        self,
        guild: discord.Guild,
        channel_id: int,
        message: discord.Message,
        member: discord.Member,
        source: str = "reaction",
    ) -> tuple[bool, str]:
        """
        Attempt to record a vote for `member` on `message` in `channel_id`.

        Returns (success: bool, reason: str).
        `source` is either "reaction" or "manual" — used only for log embed labeling.
        """
        # Enforce join age
        if member.joined_at is None or (datetime.now(timezone.utc) - member.joined_at) < timedelta(days=MIN_JOIN_DAYS):
            return False, f"Member hasn't been in the server for {MIN_JOIN_DAYS} days."

        # Block duplicate concurrent calls for the same (channel, voter) pair
        lock_key = (channel_id, member.id)
        if lock_key in self._in_flight:
            return False, "Already voted in this channel."
        self._in_flight.add(lock_key)

        try:
            return await self._do_record_vote(guild, channel_id, message, member, source)
        finally:
            self._in_flight.discard(lock_key)

    async def _do_record_vote(
        self,
        guild: discord.Guild,
        channel_id: int,
        message: discord.Message,
        member: discord.Member,
        source: str,
    ) -> tuple[bool, str]:
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                "SELECT 1 FROM event_votes WHERE channel_id = %s AND voter_id = %s LIMIT 1",
                (channel_id, member.id)
            )
            already = cursor.fetchone()
            cursor.close()
            db.close()
        except Exception:
            already = None

        if already:
            return False, "Already voted in this channel."

        # Insert vote
        inserted = False
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                "INSERT IGNORE INTO event_votes (guild_id, channel_id, message_id, voter_id) VALUES (%s, %s, %s, %s)",
                (guild.id, channel_id, message.id, member.id)
            )
            inserted = cursor.rowcount == 1
            cursor.close()
            db.close()
        except Exception:
            inserted = False

        if not inserted:
            return False, "Already voted in this channel."

        # Update in-memory tally
        self.votes[channel_id][member.id] += 1

        # Log to vote log channel
        log_channel = guild.get_channel(VOTE_LOG_CHANNEL_ID)
        if log_channel is None:
            log_channel = await guild.fetch_channel(VOTE_LOG_CHANNEL_ID) if guild else None  # type: ignore[assignment]
        if isinstance(log_channel, (discord.TextChannel, discord.Thread)):
            try:
                msg_link = f"https://discord.com/channels/{guild.id}/{channel_id}/{message.id}"
                label = "New Vote" if source == "reaction" else "Vote Added Manually"
                embed = discord.Embed(
                    title=label,
                    description=(
                        f"**User:** <@{member.id}>\n"
                        f"**Channel:** <#{channel_id}>\n"
                        f"**Message:** [jump to message]({msg_link})"
                    ),
                    color=discord.Color.blue() if source == "reaction" else discord.Color.purple()
                )
                for a in message.attachments:
                    if a.content_type and a.content_type.startswith("image"):
                        embed.set_image(url=a.url)
                        break
                await log_channel.send(embed=embed)
            except Exception:
                pass

        return True, "Vote recorded."

    # -------------------------
    # $newevent
    # -------------------------
    @commands.command(name="newevent")
    @commands.has_permissions(manage_channels=True)
    async def new_event(self, ctx: commands.Context, *, name: str):
        """Create a new text channel under EVENTS_CATEGORY_ID."""
        if not self._claim_command_once(ctx, "newevent"):
            return

        guild = ctx.guild
        if guild is None:
            await ctx.send("This command must be used in a server.")
            return

        category = guild.get_channel(EVENTS_CATEGORY_ID)
        if category is None or not isinstance(category, discord.CategoryChannel):
            await ctx.send("Event category not found. Please check configuration.")
            return

        channel_name = name.lower().replace(" ", "-")[:100]
        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            reason=f"Event channel created by {ctx.author} via $newevent"
        )

        await ctx.send(embed=discord.Embed(
            title="Event Created",
            description=f"Created event channel {channel.mention}",
            color=discord.Color.green()
        ))

        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                "REPLACE INTO event_channels (channel_id, name, created_by) VALUES (%s, %s, %s)",
                (channel.id, channel_name, ctx.author.id)
            )
            cursor.close()
            db.close()
        except Exception:
            pass

        start_embed = discord.Embed(
            title=f"Event: {name}",
            description="Voting is currently inactive. Use `$start` in this channel to begin voting.",
            color=discord.Color.blurple()
        )
        if guild.icon:
            start_embed.set_thumbnail(url=guild.icon.url)
        await channel.send(embed=start_embed)

    # -------------------------
    # $info
    # -------------------------
    @commands.command(name="info")
    @commands.has_permissions(manage_messages=True)
    async def info(self, ctx: commands.Context, *, message: str):
        """Send an informational embed with the server icon as thumbnail."""
        if not self._claim_command_once(ctx, "info"):
            return

        guild = ctx.guild
        embed = discord.Embed(title="Event Info", description=message, color=discord.Color.teal())
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=embed)

    # -------------------------
    # $start
    # -------------------------
    @commands.command(name="start")
    @commands.has_permissions(manage_channels=True)
    async def start_voting(self, ctx: commands.Context):
        """Enable voting in the current channel."""
        if not self._claim_command_once(ctx, "start"):
            return

        channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("This command must be used in a text channel.")
            return

        self.active_channels.add(channel.id)

        # Persist
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                "REPLACE INTO active_voting_channels (channel_id, started_by) VALUES (%s, %s)",
                (channel.id, ctx.author.id)
            )
            cursor.close()
            db.close()
        except Exception:
            pass

        await ctx.send(embed=discord.Embed(
            title="Voting Started",
            description=(
                f"Voting is now active in {channel.mention}. "
                f"Only members in the server for {MIN_JOIN_DAYS}+ days can vote."
            ),
            color=discord.Color.green()
        ))

        # React to recent image messages so existing submissions are covered
        async for msg in channel.history(limit=200):
            if is_image_message(msg):
                try:
                    await msg.add_reaction(VOTING_PARTIAL)
                except Exception:
                    pass

    # -------------------------
    # $stop
    # -------------------------
    @commands.command(name="stop")
    @commands.has_permissions(manage_channels=True)
    async def stop_voting(self, ctx: commands.Context):
        """Disable voting in the current channel."""
        if not self._claim_command_once(ctx, "stop"):
            return

        channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("This command must be used in a text channel.")
            return

        if channel.id not in self.active_channels:
            await ctx.send("Voting is not active in this channel.")
            return

        self.active_channels.remove(channel.id)
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("DELETE FROM active_voting_channels WHERE channel_id = %s", (channel.id,))
            cursor.close()
            db.close()
        except Exception:
            pass

        await ctx.send(embed=discord.Embed(
            title="Voting Stopped",
            description=f"Voting has been stopped in {channel.mention}.",
            color=discord.Color.orange()
        ))

    # -------------------------
    # $vote  (log channel only)
    # -------------------------
    @commands.command(name="vote")
    async def show_top_voter(self, ctx: commands.Context, channel_id: Optional[int] = None):
        """Show current top voter(s). Only usable inside the vote log channel."""
        if not self._claim_command_once(ctx, "vote"):
            return

        # Restrict to commands channel only
        if ctx.channel.id != COMMANDS_CHANNEL_ID:
            cmd_ch = ctx.guild.get_channel(COMMANDS_CHANNEL_ID) if ctx.guild else None
            mention = cmd_ch.mention if isinstance(cmd_ch, discord.TextChannel) else f"<#{COMMANDS_CHANNEL_ID}>"
            await ctx.send(embed=discord.Embed(
                title="Wrong Channel",
                description=f"This command can only be used in {mention}.",
                color=discord.Color.red()
            ))
            return

        # Resolve target channel
        if channel_id is not None:
            if ctx.guild is None:
                await ctx.send("This command must be used in a server.")
                return
            target_channel = ctx.guild.get_channel(channel_id)
            if target_channel is None or not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
                await ctx.send(embed=discord.Embed(
                    title="Channel Not Found",
                    description=f"No text/thread channel found with ID `{channel_id}`.",
                    color=discord.Color.red()
                ))
                return
        else:
            await ctx.send(embed=discord.Embed(
                title="Missing Argument",
                description="Please provide a channel ID: `$vote <channel_id>`",
                color=discord.Color.red()
            ))
            return

        # Fetch votes from DB
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                "SELECT voter_id, COUNT(*) as cnt FROM event_votes WHERE channel_id = %s GROUP BY voter_id",
                (target_channel.id,)
            )
            rows = cursor.fetchall() or []
            cursor.close()
            db.close()
        except Exception:
            rows = []

        if not rows:
            await ctx.send("No votes recorded for that channel yet.")
            return

        top_count = max(r[1] for r in rows)
        top_users = [r[0] for r in rows if r[1] == top_count]
        mentions = ", ".join(f"<@{uid}> ({top_count})" for uid in top_users)

        event_name = None
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("SELECT name FROM event_channels WHERE channel_id = %s", (target_channel.id,))
            res = cursor.fetchone()
            cursor.close()
            db.close()
            if res:
                event_name = res[0]
        except Exception:
            pass

        title = f"Top Voter(s) — {event_name}" if event_name else f"Top Voter(s) for {target_channel.mention}"
        await ctx.send(embed=discord.Embed(title=title, description=mentions, color=discord.Color.gold()))

    # -------------------------
    # $leaderboard  (manage channels, commands channel only)
    # -------------------------
    @commands.command(name="leaderboard")
    @commands.has_permissions(manage_channels=True)
    async def leaderboard(self, ctx: commands.Context, channel_id: Optional[int] = None):
        """Show top 10 voters for a channel. Usage: $leaderboard <channel_id>"""
        if not self._claim_command_once(ctx, "leaderboard"):
            return

        # Restrict to commands channel only
        if ctx.channel.id != COMMANDS_CHANNEL_ID:
            cmd_ch = ctx.guild.get_channel(COMMANDS_CHANNEL_ID) if ctx.guild else None
            mention = cmd_ch.mention if isinstance(cmd_ch, discord.TextChannel) else f"<#{COMMANDS_CHANNEL_ID}>"
            await ctx.send(embed=discord.Embed(
                title="Wrong Channel",
                description=f"This command can only be used in {mention}.",
                color=discord.Color.red()
            ))
            return

        if channel_id is None:
            await ctx.send(embed=discord.Embed(
                title="Missing Argument",
                description="Please provide a channel ID: `$leaderboard <channel_id>`",
                color=discord.Color.red()
            ))
            return

        if ctx.guild is None:
            await ctx.send("This command must be used in a server.")
            return

        target_channel = ctx.guild.get_channel(channel_id)
        if target_channel is None or not isinstance(target_channel, (discord.TextChannel, discord.Thread)):
            await ctx.send(embed=discord.Embed(
                title="Channel Not Found",
                description=f"No text/thread channel found with ID `{channel_id}`.",
                color=discord.Color.red()
            ))
            return

        # Fetch top 10 from DB ordered by vote count descending
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute(
                """
                SELECT message_id, COUNT(*) as cnt
                FROM event_votes
                WHERE channel_id = %s
                GROUP BY message_id
                ORDER BY cnt DESC
                LIMIT 10
                """,
                (target_channel.id,)
            )
            rows = cursor.fetchall() or []
            cursor.close()
            db.close()
        except Exception:
            rows = []

        if not rows:
            await ctx.send("No votes recorded for that channel yet.")
            return

        # Fetch event name if available
        event_name = None
        try:
            db = get_db()
            cursor = db.cursor()
            cursor.execute("SELECT name FROM event_channels WHERE channel_id = %s", (target_channel.id,))
            res = cursor.fetchone()
            cursor.close()
            db.close()
            if res:
                event_name = res[0]
        except Exception:
            pass

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for i, (message_id, cnt) in enumerate(rows, start=1):
            prefix = medals.get(i, f"**#{i}**")
            lines.append(f"{prefix} https://discord.com/channels/{ctx.guild.id}/{target_channel.id}/{message_id} — {cnt} vote{'s' if cnt != 1 else ''}")

        title = f"Leaderboard — {event_name}" if event_name else f"Leaderboard for {target_channel.mention}"
        embed = discord.Embed(
            title=title,
            description="\n".join(lines),
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Showing top {len(rows)} winner(s)")
        await ctx.send(embed=embed)

    # -------------------------
    # $addvote  (admin, commands channel only)
    # -------------------------
    @commands.command(name="addvote")
    @commands.has_permissions(administrator=True)
    async def add_vote(self, ctx: commands.Context, user_id: int, message_id: int):
        """
        Manually add a vote for a user on a specific message.
        Usage: $addvote <user_id> <message_id>
        Must be used in the vote log channel. The message must belong to an active voting channel.
        """
        if not self._claim_command_once(ctx, "addvote"):
            return

        # Restrict to commands channel
        if ctx.channel.id != COMMANDS_CHANNEL_ID:
            cmd_ch = ctx.guild.get_channel(COMMANDS_CHANNEL_ID) if ctx.guild else None
            mention = cmd_ch.mention if isinstance(cmd_ch, discord.TextChannel) else f"<#{COMMANDS_CHANNEL_ID}>"
            await ctx.send(embed=discord.Embed(
                title="Wrong Channel",
                description=f"This command can only be used in {mention}.",
                color=discord.Color.red()
            ))
            return

        guild = ctx.guild
        if guild is None:
            await ctx.send("This command must be used in a server.")
            return

        # Resolve member
        member = guild.get_member(user_id)
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except Exception:
                member = None

        if member is None:
            await ctx.send(embed=discord.Embed(
                title="User Not Found",
                description=f"No member found with ID `{user_id}`.",
                color=discord.Color.red()
            ))
            return

        # Enforce join age
        if member.joined_at is None or (datetime.now(timezone.utc) - member.joined_at) < timedelta(days=MIN_JOIN_DAYS):
            await ctx.send(embed=discord.Embed(
                title="Ineligible Member",
                description=f"{member.mention} hasn't been in the server for {MIN_JOIN_DAYS} days and cannot be voted for.",
                color=discord.Color.red()
            ))
            return

        # Find the message — search all active voting channels
        target_message: Optional[discord.Message] = None
        target_channel_id: Optional[int] = None

        for cid in self.active_channels:
            ch = guild.get_channel(cid)
            if ch is None or not hasattr(ch, "fetch_message"):
                continue
            try:
                target_message = await ch.fetch_message(message_id)  # type: ignore[call-arg]
                target_channel_id = cid
                break
            except Exception:
                continue

        if target_message is None or target_channel_id is None:
            await ctx.send(embed=discord.Embed(
                title="Message Not Found",
                description=(
                    f"Could not find message `{message_id}` in any active voting channel. "
                    "Make sure voting is started in that channel."
                ),
                color=discord.Color.red()
            ))
            return

        # Verify the message contains an image
        if not is_image_message(target_message):
            await ctx.send(embed=discord.Embed(
                title="Not an Image Post",
                description="The target message does not contain an image and cannot receive votes.",
                color=discord.Color.red()
            ))
            return

        # Record the vote
        success, reason = await self._record_vote(
            guild=guild,
            channel_id=target_channel_id,
            message=target_message,
            member=member,
            source="manual",
        )

        if success:
            await ctx.send(embed=discord.Embed(
                title="Vote Added",
                description=(
                    f"Successfully added a vote for {member.mention} on "
                    f"[this message](https://discord.com/channels/{guild.id}/{target_channel_id}/{message_id})."
                ),
                color=discord.Color.green()
            ))
        else:
            await ctx.send(embed=discord.Embed(
                title="Vote Not Added",
                description=f"Could not add vote: {reason}",
                color=discord.Color.orange()
            ))

    # -------------------------
    # on_message: auto-react to images
    # -------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        if message.channel.id not in self.active_channels:
            return
        if is_image_message(message):
            try:
                await message.add_reaction(VOTING_PARTIAL)
            except Exception:
                pass

    # -------------------------
    # on_raw_reaction_add: handle user votes
    # -------------------------
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not self.bot.user:
            return
        if payload.user_id == self.bot.user.id:
            return
        if payload.guild_id is None:
            return

        def _emoji_matches(e) -> bool:
            eid = getattr(e, "id", None)
            name = getattr(e, "name", None)
            if eid is not None and VOTING_EMOJI_ID is not None:
                return eid == VOTING_EMOJI_ID
            if name is not None:
                return name == VOTING_EMOJI_NAME or str(e) == VOTING_EMOJI_STR
            return str(e) == VOTING_EMOJI_STR

        if not _emoji_matches(payload.emoji):
            return

        channel_id = payload.channel_id
        if channel_id not in self.active_channels:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = guild.get_member(payload.user_id)
        if member is None:
            try:
                member = await guild.fetch_member(payload.user_id)
            except Exception:
                member = None

        channel = guild.get_channel(channel_id)
        if channel is None or not hasattr(channel, "fetch_message"):
            return

        try:
            message = await channel.fetch_message(payload.message_id)  # type: ignore[call-arg]
        except Exception:
            return

        emoji_obj = (
            discord.PartialEmoji(name=payload.emoji.name, id=payload.emoji.id)
            if getattr(payload.emoji, "id", None) is not None
            else str(payload.emoji)
        )

        # Always remove the visible reaction immediately to keep count hidden
        try:
            await message.remove_reaction(emoji_obj, member or discord.Object(id=payload.user_id))
        except Exception:
            pass

        if member is None:
            return

        # Record the vote (join-age check, dupe check, DB insert, and logging all handled inside)
        success, reason = await self._record_vote(
            guild=guild,
            channel_id=channel_id,
            message=message,
            member=member,
            source="reaction",
        )

        if not success:
            try:
                user = await self.bot.fetch_user(payload.user_id)
                if reason == "Already voted in this channel.":
                    await user.send("You have already voted in this event; only one vote is allowed.")
                elif "30 days" in reason:
                    await user.send(
                        f"You must be in the server for at least {MIN_JOIN_DAYS} days to vote in this event."
                    )
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(EventCog(bot))