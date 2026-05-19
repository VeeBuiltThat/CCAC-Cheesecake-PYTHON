import discord
from discord.ext import commands

# UI imports may vary by discord.py version. TextInput (modals) may not be available on older versions.
try:
    from discord.ui import View, Button, Modal, TextInput
    TEXT_INPUT_AVAILABLE = True
except Exception:
    from discord.ui import View, Button, Modal
    TextInput = None
    TEXT_INPUT_AVAILABLE = False
from typing import Optional, Type, cast, Any
from . import config
from .db import Database
from discord.ext import tasks

# Typed modal symbols for static analysis and runtime assignment
EmergencyApplyModal: Optional[Type[Modal]] = None
RejectReasonModal: Optional[Type[Modal]] = None



# Channel IDs from user request
EMERGENCY_CHANNEL_ID = 1435610754425294940  # where the rules embed will be
STAFF_REVIEW_CHANNEL_ID = 1431344160840880159  # where staff review embeds will be sent
POSTING_CHANNEL_ID = 1245431550942904341  # approved posts go here
LOGS_CHANNEL_ID = 1430575592503378142  # logs for accepted/rejected


RULES_DESCRIPTION = """
## __Rules__ <:Icon_coffeecup:1244408317535846471>
<:zNumber_1:1245399268622205113> All emergency commissions must follow our pre-established server rules, **including the budget rule**.

<:zNumber_2:1245399319612362803> You must apply via the ticket system in order to have your comms posted. We are keeping it to one post per emergency in order to ensure everyone is seen. Please select “General Questions” from the drop-down menu.

<:zNumber_3:1245399585430438070> Staff will determine if your emergency meets the criteria to post in the channel and you will be asked to provide proof. If it doesn’t, you can still post your emergency in the normal selling channels. If it does, we will create the post for you via our bots.

<:zNumber_4:1245399634638274560> You may apply for one emergency per 2 months. We will also delete ads over two months old. This is to avoid abuse of the system and flooding of the channel. Abuse of this system will result in disqualification from access to the emergency commission channel altogether.
<:zNumber_5:1245399682939748436> Users should report any attempt to haggle down pricing, Please do not allow others to convince you to take less. Even if you’re in an emergency, you still deserve fair compensation for your work!

<:zNumber_6:1245399728389095575> Users are required to include a set number of slots in their post and update it as they open / close. This will help staff ensure commissions are being completed and you aren’t being overwhelmed. This will be done using reactions, so you will be expected to react to your emergency with the number of slots open and update it yourself.

<:zNumber_7:1245399830470070292> Fundraiser links may **NOT** be posted here, this is exclusively for emergency commissions, as you are offering a service. These links CAN be posted in advertising socials, however.

**Please note, you will be asked to provide evidence of your emergency. We will not ask to see any sensitive information, but we may ask to see the total amount of a bill you owe for example**
## __Qualifying Emergencies__ <:Icon_jello:1244408406350106654>

<:zNumber_1:1245399268622205113> Bills necessary for life & schooling ( rent, electric, water, wifi, phone, etc )
<:zNumber_2:1245399319612362803> Medical bills ( incl. human & vet bills along with medications )
<:zNumber_3:1245399585430438070> Natural disaster impact relief
<:zNumber_4:1245399634638274560> Food / groceries
<:zNumber_5:1245399682939748436> Transportation to work/school/doctor ( gas or bus fare for example )
<:zNumber_6:1245399728389095575> Funeral / cremation services

**It is ultimately up to staff discretion whether or not your emergency will be accepted. This list is non-exhaustive, meaning if we deem another situation an emergency it may be posted.**
"""


if TEXT_INPUT_AVAILABLE:
    # cast TextInput to Any for static analysis so the checker knows it's callable here
    _TextInput = cast(Any, TextInput)

    class _EmergencyApplyModal(Modal, title="Apply for Emergency Commission"):
        def __init__(self):
            super().__init__()
            self.emergency = _TextInput(label="Emergency matter", style=discord.TextStyle.short, placeholder="Briefly describe the emergency", required=True, max_length=200)
            self.slots = _TextInput(label="Slots open", style=discord.TextStyle.short, placeholder="e.g. 1, 2, or 3 slots", required=True, max_length=20)
            self.info = _TextInput(label="Commission information", style=discord.TextStyle.long, placeholder="Describe what you are offering and any important details", required=True, max_length=2000)
            self.add_item(self.emergency)
            self.add_item(self.slots)
            self.add_item(self.info)

        async def on_submit(self, interaction: discord.Interaction):
            # Create embed for staff review
            applicant = interaction.user
            embed = discord.Embed(title="Emergency Commission Application", color=discord.Color.orange())
            embed.set_author(name=str(applicant), icon_url=applicant.display_avatar.url)
            embed.add_field(name="Emergency matter", value=self.emergency.value, inline=False)
            embed.add_field(name="Slots open", value=self.slots.value, inline=True)
            embed.add_field(name="Commission information", value=self.info.value[:1000], inline=False)
            embed.set_footer(text=f"Applicant ID: {applicant.id}")

            # Insert application into DB (if available) and attach application id to the view
            db = getattr(interaction.client, 'db', None)
            app_id = None
            if db is not None:
                try:
                    app_id = await db.insert_application(applicant.id, applicant.mention, self.emergency.value, self.slots.value, self.info.value, None)
                except Exception:
                    app_id = None

            view = StaffReviewView(applicant.id, applicant.mention, embed, application_id=app_id)

            staff_channel = interaction.client.get_channel(STAFF_REVIEW_CHANNEL_ID)
            from discord import TextChannel
            if not isinstance(staff_channel, TextChannel):
                await interaction.response.send_message("⚠️ Staff review channel not found or is not a text channel. Please contact an admin.", ephemeral=True)
                return

            staff_msg = await staff_channel.send(embed=embed, view=view)
            # update staff_message_id in DB if possible
            if db is not None and app_id is not None:
                try:
                    await db.update_staff_message_id(app_id, staff_msg.id)
                except Exception:
                    pass

            await interaction.response.send_message("✅ Your application has been submitted for staff review.", ephemeral=True)


    class _RejectReasonModal(Modal, title="Rejection Reason"):
        def __init__(self, applicant_id: int, applicant_mention: str, orig_embed: discord.Embed, message: Optional[discord.Message], application_id: Optional[int] = None):
            super().__init__()
            self.applicant_id = applicant_id
            self.applicant_mention = applicant_mention
            self.orig_embed = orig_embed
            self.orig_message = message
            self.application_id = application_id
            self.reason = _TextInput(label="Reason for rejection", style=discord.TextStyle.long, placeholder="Explain why this application was rejected", required=True, max_length=1000)
            self.add_item(self.reason)

        async def on_submit(self, interaction: discord.Interaction):
            staff_member = interaction.user
            reason_text = self.reason.value

            # DM the applicant
            try:
                applicant_user = await interaction.client.fetch_user(self.applicant_id)
                dm_embed = discord.Embed(title="Your emergency commission application was rejected", color=discord.Color.red())
                dm_embed.add_field(name="Reason", value=reason_text, inline=False)
                dm_embed.set_footer(text=f"Handled by {staff_member}")
                await applicant_user.send(embed=dm_embed)
            except Exception:
                # ignore failures when DMing
                pass

            # Update DB if available
            db = getattr(interaction.client, 'db', None)
            if db is not None and getattr(self, 'application_id', None) is not None:
                try:
                    await db.reject_application(self.application_id, staff_member.id if hasattr(staff_member, 'id') else None, reason_text)
                except Exception:
                    pass

            # Log the rejection
            from discord import TextChannel
            logs_channel = interaction.client.get_channel(LOGS_CHANNEL_ID)
            if isinstance(logs_channel, TextChannel):
                log_embed = discord.Embed(title="Application Rejected", color=discord.Color.red())
                log_embed.add_field(name="Applicant", value=self.applicant_mention, inline=True)
                log_embed.add_field(name="Staff", value=str(staff_member), inline=True)
                log_embed.add_field(name="Reason", value=reason_text, inline=False)
                if getattr(self, 'application_id', None) is not None:
                    log_embed.add_field(name="Application ID", value=str(self.application_id), inline=True)
                await logs_channel.send(embed=log_embed)

            # Disable buttons on original message if possible
            try:
                if self.orig_message and hasattr(self.orig_message, 'edit'):
                    await self.orig_message.edit(view=None)
            except Exception:
                pass

            await interaction.response.send_message("✅ Rejection recorded and applicant notified.", ephemeral=True)

    # Expose typed modal class names for static analysis and runtime use
    EmergencyApplyModal = cast(Type[Modal], _EmergencyApplyModal)
    RejectReasonModal = cast(Type[Modal], _RejectReasonModal)
else:
    EmergencyApplyModal = None
    RejectReasonModal = None


class StaffReviewView(View):
    def __init__(self, applicant_id: int, applicant_mention: str, orig_embed: discord.Embed, application_id: Optional[int]=None, timeout: Optional[float]=None):
        super().__init__(timeout=timeout)
        self.applicant_id = applicant_id
        self.applicant_mention = applicant_mention
        self.orig_embed = orig_embed
        self.application_id = application_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Only allow staff with manage_guild or manage_messages perms to act
        member = interaction.user
        if not isinstance(member, discord.Member):
            await interaction.response.send_message("⚠️ Only server members with staff permissions can use this.", ephemeral=True)
            return False
        perms = member.guild_permissions
        if not (perms.manage_guild or perms.manage_messages or perms.manage_roles):
            await interaction.response.send_message("⚠️ You do not have permission to use this.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        staff_member = interaction.user

        # Post to main posting channel
        from discord import TextChannel
        posting_channel = interaction.client.get_channel(POSTING_CHANNEL_ID)
        if isinstance(posting_channel, TextChannel):
            public_embed = discord.Embed(title="Emergency Commission", color=discord.Color.green())
            public_embed.set_author(name=self.orig_embed.author.name if self.orig_embed.author else "", icon_url=self.orig_embed.author.icon_url if self.orig_embed.author else None)
            # copy fields from orig
            for f in self.orig_embed.fields:
                public_embed.add_field(name=f.name, value=f.value, inline=f.inline)
            public_embed.set_footer(text=f"Posted by staff: {staff_member}")
            posting_msg = await posting_channel.send(embed=public_embed)
            # Update DB for accepted application
            db = getattr(interaction.client, 'db', None)
            if db is not None and getattr(self, 'application_id', None) is not None:
                try:
                    await db.accept_application(self.application_id, posting_channel.id, posting_msg.id, getattr(staff_member, 'id', None))
                except Exception:
                    pass

        # DM applicant about acceptance
        try:
            applicant_user = await interaction.client.fetch_user(self.applicant_id)
            dm_embed = discord.Embed(title="Your emergency commission was accepted!", color=discord.Color.green())
            for f in self.orig_embed.fields:
                dm_embed.add_field(name=f.name, value=f.value, inline=f.inline)
            dm_embed.set_footer(text="Thank you — staff will post it in the emergency channel shortly.")
            await applicant_user.send(embed=dm_embed)
        except Exception:
            pass

        # Log acceptance
        from discord import TextChannel
        logs_channel = interaction.client.get_channel(LOGS_CHANNEL_ID)
        if isinstance(logs_channel, TextChannel):
            log_embed = discord.Embed(title="Application Accepted", color=discord.Color.green())
            log_embed.add_field(name="Applicant", value=self.applicant_mention, inline=True)
            log_embed.add_field(name="Staff", value=str(staff_member), inline=True)
            if getattr(self, 'application_id', None) is not None:
                log_embed.add_field(name="Application ID", value=str(self.application_id), inline=True)
            await logs_channel.send(embed=log_embed)

        # disable buttons
        for child in self.children:
            if isinstance(child, Button):
                child.disabled = True
        try:
            if interaction.message:
                await interaction.message.edit(view=self)
        except Exception:
            pass

        await interaction.response.send_message("✅ Application accepted and posted.", ephemeral=True)

    @discord.ui.button(label="Reject", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        # If TextInput modals are available, open modal; otherwise DM staff for a reason
        staff_member = interaction.user
        try:
            if TEXT_INPUT_AVAILABLE and RejectReasonModal is not None:
                modal_ctor = cast(Any, RejectReasonModal)
                modal = modal_ctor(self.applicant_id, self.applicant_mention, self.orig_embed, interaction.message, getattr(self, 'application_id', None))
                await interaction.response.send_modal(modal)
                return

            # DM the staff member to get a rejection reason (embed-based)
            await interaction.response.send_message("📩 Please check your DMs to submit a rejection reason.", ephemeral=True)
            dm = await staff_member.create_dm()
            prompt = discord.Embed(title="Reject Application", description=f"Please reply with the reason to reject the application from {self.applicant_mention} (ID: {self.applicant_id}). You have 10 minutes.", color=discord.Color.red())
            await dm.send(embed=prompt)

            def check_staff_dm(m: discord.Message):
                return m.author.id == staff_member.id and isinstance(m.channel, discord.DMChannel)

            reason_msg = await interaction.client.wait_for('message', check=check_staff_dm, timeout=600)
            reason_text = reason_msg.content

            # DM the applicant
            try:
                applicant_user = await interaction.client.fetch_user(self.applicant_id)
                dm_embed = discord.Embed(title="Your emergency commission application was rejected", color=discord.Color.red())
                dm_embed.add_field(name="Reason", value=reason_text, inline=False)
                dm_embed.set_footer(text=f"Handled by {staff_member}")
                await applicant_user.send(embed=dm_embed)
            except Exception:
                # ignore failures when DMing applicant
                pass

            # Update DB if available
            db = getattr(interaction.client, 'db', None)
            if db is not None and getattr(self, 'application_id', None) is not None:
                try:
                    await db.reject_application(self.application_id, staff_member.id if hasattr(staff_member, 'id') else None, reason_text)
                except Exception:
                    pass

            # Log the rejection
            from discord import TextChannel
            logs_channel = interaction.client.get_channel(LOGS_CHANNEL_ID)
            if isinstance(logs_channel, TextChannel):
                log_embed = discord.Embed(title="Application Rejected (DM)", color=discord.Color.red())
                log_embed.add_field(name="Applicant", value=self.applicant_mention, inline=True)
                log_embed.add_field(name="Staff", value=str(staff_member), inline=True)
                log_embed.add_field(name="Reason", value=reason_text, inline=False)
                if getattr(self, 'application_id', None) is not None:
                    log_embed.add_field(name="Application ID", value=str(self.application_id), inline=True)
                await logs_channel.send(embed=log_embed)

            # Disable buttons on original message and edit
            for child in self.children:
                if isinstance(child, Button):
                    child.disabled = True
            try:
                if interaction.message:
                    await interaction.message.edit(view=self)
            except Exception:
                pass

            try:
                await dm.send(embed=discord.Embed(title="Rejection Sent", description="The applicant has been notified and the rejection was logged.", color=discord.Color.green()))
            except Exception:
                pass
        except Exception:
            try:
                await interaction.response.send_message("⚠️ Failed to process rejection. You can use the `reject_emergency` fallback command.", ephemeral=True)
            except Exception:
                pass


class Emergency(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db: Optional[Database] = None

    async def initialize(self) -> None:
        """Create DB tables and start background cleanup."""
        try:
            self.db = Database()
            await self.db.create_tables()
            # expose a convenient reference for other code paths
            setattr(self.bot, 'db', self.db)
        except Exception as e:
            print("Warning: failed to initialize database:", e)
            self.db = None

        # Run one cleanup at startup, then start periodic task
        try:
            await self.run_cleanup_once()
        except Exception:
            pass
        try:
            self.cleanup_task.start()
        except Exception:
            pass

    async def run_cleanup_once(self) -> None:
        """Run one-pass cleanup for expired posts (safe to call on startup)."""
        if not self.db:
            return
        try:
            expired = await self.db.find_expired_posts(60)
            for row in expired:
                try:
                    chan = self.bot.get_channel(row['posting_channel_id'])
                    from discord import TextChannel
                    if isinstance(chan, TextChannel):
                        try:
                            msg = await chan.fetch_message(row['posting_message_id'])
                            await msg.delete()
                        except Exception:
                            pass
                    await self.db.mark_deleted(row['id'])
                    logs = self.bot.get_channel(LOGS_CHANNEL_ID)
                    if isinstance(logs, TextChannel):
                        embed = discord.Embed(title="Expired Emergency Post Deleted", description=f"Application ID: {row['id']}\nApplicant: {row['applicant_mention']}", color=discord.Color.orange())
                        await logs.send(embed=embed)
                except Exception:
                    pass
        except Exception as e:
            print("Error running emergency cleanup once:", e)

    @tasks.loop(hours=24)
    async def cleanup_task(self) -> None:
        await self.run_cleanup_once()

    def cog_unload(self) -> None:
        try:
            self.cleanup_task.cancel()
        except Exception:
            pass

    @commands.command(name="post_emergency_rules")
    @commands.has_permissions(manage_guild=True)
    async def post_rules(self, ctx: commands.Context):
        """Post the emergency commission rules embed and attach the Apply button"""
        embed = discord.Embed(title="Emergency Commissions - Rules & Qualifying Emergencies", description=RULES_DESCRIPTION, color=discord.Color.brand_green() if hasattr(discord.Color, 'brand_green') else discord.Color.teal())
        embed.set_footer(text="Click the button below to apply — a staff member will review your application.")

        view = View()
        apply_btn = Button(label="Apply for emergency commission", style=discord.ButtonStyle.blurple)

        async def apply_cb(interaction: discord.Interaction):
                # Always collect application via DM-based embedded prompts
            try:
                await interaction.response.send_message("📩 I've DM'd you a short application form.", ephemeral=True)
            except Exception:
                pass

            user = interaction.user
            try:
                dm_channel = await user.create_dm()

                # Step 1: Emergency matter
                prompt1 = discord.Embed(title="Emergency Application — Step 1 of 3", description="Please reply with your emergency matter (brief). You have 5 minutes.", color=discord.Color.orange())
                await dm_channel.send(embed=prompt1)

                def check_dm(m: discord.Message):
                    return m.author.id == user.id and isinstance(m.channel, discord.DMChannel)

                emergency_msg = await interaction.client.wait_for('message', check=check_dm, timeout=300)

                # Step 2: Slots
                prompt2 = discord.Embed(title="Emergency Application — Step 2 of 3", description="Reply with the number of slots open (e.g., 1, 2, or 3). You have 5 minutes.", color=discord.Color.orange())
                await dm_channel.send(embed=prompt2)
                slots_msg = await interaction.client.wait_for('message', check=check_dm, timeout=300)

                # Step 3: Commission info
                prompt3 = discord.Embed(title="Emergency Application — Step 3 of 3", description="Please send the commission information (you have 10 minutes). Try to keep it concise.", color=discord.Color.orange())
                await dm_channel.send(embed=prompt3)
                info_msg = await interaction.client.wait_for('message', check=check_dm, timeout=600)

                # Build embed and post to staff review channel
                embed = discord.Embed(title="Emergency Commission Application (DM)", color=discord.Color.orange())
                embed.set_author(name=str(user), icon_url=user.display_avatar.url)
                embed.add_field(name="Emergency matter", value=emergency_msg.content[:1000], inline=False)
                embed.add_field(name="Slots open", value=slots_msg.content[:1000], inline=True)
                embed.add_field(name="Commission information", value=info_msg.content[:1000], inline=False)
                embed.set_footer(text=f"Applicant ID: {user.id}")

                from discord import TextChannel
                staff_channel = interaction.client.get_channel(STAFF_REVIEW_CHANNEL_ID)
                db = getattr(interaction.client, 'db', None)
                app_id = None
                if db is not None:
                    try:
                        app_id = await db.insert_application(user.id, user.mention, emergency_msg.content, slots_msg.content, info_msg.content, None)
                    except Exception:
                        app_id = None

                if isinstance(staff_channel, TextChannel):
                    view = StaffReviewView(user.id, user.mention, embed, application_id=app_id)
                    staff_msg = await staff_channel.send(embed=embed, view=view)
                    if db is not None and app_id is not None:
                        try:
                            await db.update_staff_message_id(app_id, staff_msg.id)
                        except Exception:
                            pass

                done_embed = discord.Embed(title="Application Submitted", description="Your application has been submitted for staff review. We will contact you if we need more information.", color=discord.Color.green())
                await dm_channel.send(embed=done_embed)
            except Exception:
                try:
                    await interaction.user.send("⚠️ I couldn't DM you. Please open a ticket or contact staff manually.")
                except Exception:
                    pass
                return

        apply_btn.callback = apply_cb
        view.add_item(apply_btn)

        dest = None
        if ctx.guild:
            dest = ctx.guild.get_channel(EMERGENCY_CHANNEL_ID)
        if dest is None:
            # fallback: try fetch
            try:
                dest = await self.bot.fetch_channel(EMERGENCY_CHANNEL_ID)
            except Exception:
                dest = None
        from discord import TextChannel
        if not isinstance(dest, TextChannel):
            await ctx.send("⚠️ Emergency channel not found or is not a text channel.")
            return

        # send the embed
        await dest.send(embed=embed, view=view)
        await ctx.send("✅ Rules posted.")

    @commands.command(name="reject_emergency")
    @commands.has_permissions(manage_guild=True)
    async def reject_emergency(self, ctx: commands.Context, applicant_id: int, *, reason: str):
        """Staff fallback to reject an application when modals aren't available.

        Sends a DM to the applicant and logs the rejection in the logs channel.
        """
        # DM applicant
        try:
            user = await ctx.bot.fetch_user(applicant_id)
            dm_embed = discord.Embed(title="Your emergency commission application was rejected", color=discord.Color.red())
            dm_embed.add_field(name="Reason", value=reason, inline=False)
            dm_embed.set_footer(text=f"Handled by {ctx.author}")
            await user.send(embed=dm_embed)
        except Exception:
            pass

        # Try to mark the latest pending application for this applicant as rejected in the DB (best-effort)
        db = getattr(ctx.bot, 'db', None)
        from discord import TextChannel
        logs_channel = ctx.bot.get_channel(LOGS_CHANNEL_ID)
        if db is not None:
            try:
                row = await db.fetchone("SELECT id FROM emergency_applications WHERE applicant_id=%s AND status='pending' ORDER BY created_at DESC LIMIT 1", (applicant_id,))
                if row:
                    try:
                        await db.reject_application(row['id'], getattr(ctx.author,'id',None), reason)
                    except Exception:
                        pass
                    if isinstance(logs_channel, TextChannel):
                        # include application id in log
                        log_embed = discord.Embed(title="Application Rejected (fallback)", color=discord.Color.red())
                        log_embed.add_field(name="Applicant ID", value=str(applicant_id), inline=True)
                        log_embed.add_field(name="Application ID", value=str(row['id']), inline=True)
                        log_embed.add_field(name="Staff", value=str(ctx.author), inline=True)
                        log_embed.add_field(name="Reason", value=reason, inline=False)
                        await logs_channel.send(embed=log_embed)
                    # quick return so we don't double-log below
                    await ctx.send("✅ Rejection sent and logged (if possible).", delete_after=10)
                    return
            except Exception:
                pass

        # Log the rejection (fallback for when DB or specific application not found)
        if isinstance(logs_channel, TextChannel):
            log_embed = discord.Embed(title="Application Rejected (fallback)", color=discord.Color.red())
            log_embed.add_field(name="Applicant ID", value=str(applicant_id), inline=True)
            log_embed.add_field(name="Staff", value=str(ctx.author), inline=True)
            log_embed.add_field(name="Reason", value=reason, inline=False)
            await logs_channel.send(embed=log_embed)

        await ctx.send("✅ Rejection sent and logged (if possible).", delete_after=10)

    @commands.command(name="cleanup_emergency_posts")
    @commands.has_permissions(manage_guild=True)
    async def cleanup_emergency_posts(self, ctx: commands.Context):
        """Run the emergency post cleanup now (admin only) for testing and maintenance."""
        try:
            await self.run_cleanup_once()
            await ctx.send("✅ Cleanup run completed.")
        except Exception as e:
            await ctx.send(f"⚠️ Cleanup failed: {e}")


async def setup(bot: commands.Bot):
    cog = Emergency(bot)
    await bot.add_cog(cog)
    # initialize DB and background tasks if possible
    try:
        await cog.initialize()
    except Exception:
        pass
