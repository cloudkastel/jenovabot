from ioutils import read_sql, write_sql, DATABASE_SETTINGS

import discord, datetime
from discord.ext import commands, tasks
from discord.utils import format_dt


class EventAlerts(commands.Cog, name="Event Alerts"):
    """Send a timestamped ping message whenever an event is created for a particular role."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.yet_to_ping: set[discord.ScheduledEvent] = set()
    
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            for event in await guild.fetch_scheduled_events():
                await self.create_wait_until_announcement_task(event)
                self.yet_to_ping.add(event)

    @commands.Cog.listener()
    async def on_scheduled_event_create(self, event: discord.ScheduledEvent):
        """Send a ping message when an event tied to a role is created."""
        await self.send_event_start_time_message(event)

    @commands.Cog.listener()
    async def on_scheduled_event_update(self, before: discord.ScheduledEvent, after: discord.ScheduledEvent):
        if before.start_time != after.start_time:
            await self.send_event_start_time_message(after, rescheduling=True)
    
    async def send_event_start_time_message(self, event: discord.ScheduledEvent, *, rescheduling: bool = False):
        role = EventAlerts.get_role_from_event(event)
        if role is None:
            return
        
        channel = await event.guild.fetch_channel(read_sql(DATABASE_SETTINGS, event.guild.id, "scheduled_event_alert_channel_id"))
        if isinstance(channel, discord.ForumChannel):
            channel = EventAlerts.get_channel_from_role(channel, role)
        await channel.send(f"{event.name} {'has been rescheduled to' if rescheduling else 'is set for'} {format_dt(event.start_time, style='F')}! {role.mention} \n{event.url}")

        await self.create_wait_until_announcement_task(event)
        self.yet_to_ping.add(event)
    
    async def create_wait_until_announcement_task(self, event: discord.ScheduledEvent):
        event = await event.guild.fetch_scheduled_event(event.id)

        @tasks.loop(time=(event.start_time - datetime.timedelta(minutes=30)).timetz())
        async def wait_until_announcement():
            if datetime.datetime.now(event.start_time.tzinfo).date() == event.start_time.date():
                event_creator = await event.guild.fetch_member(event.creator.id)
                if isinstance(event_creator, discord.Member) and event_creator.voice is not None:
                    await self.send_event_is_starting_message(event)
                    wait_until_announcement.stop()

        wait_until_announcement.start()
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if not (before.channel is None and after.channel is not None): # Member has joined a voice channel
            return
        
        for event in self.yet_to_ping.copy():
            event = await event.guild.fetch_scheduled_event(event.id)
            event_creator = await EventAlerts.get_event_creator(event)
            if event_creator.id == member.id:
                await self.send_event_is_starting_message(event)
    
    async def send_event_is_starting_message(self, event: discord.ScheduledEvent):
        role = EventAlerts.get_role_from_event(event)
        time_until_event_start = event.start_time - datetime.datetime.now(event.start_time.tzinfo)
        if time_until_event_start <= datetime.timedelta(minutes=30):
            channel = await event.guild.fetch_channel(read_sql(DATABASE_SETTINGS, event.guild.id, "scheduled_event_alert_channel_id"))
            if isinstance(channel, discord.ForumChannel):
                channel = EventAlerts.get_channel_from_role(channel, role)
            await channel.send(f"{event.name} is starting {format_dt(event.start_time, style='R')}! {role.mention} \n{event.url}")
            self.yet_to_ping.remove(event)

    @commands.command()
    @commands.has_guild_permissions(manage_guild=True)
    async def alerts(self, context: commands.Context, channel: discord.TextChannel | discord.ForumChannel):
        """Set which channel to send event alert ping messages."""

        write_sql(DATABASE_SETTINGS, context.guild.id, "scheduled_event_alert_channel_id", channel.id)
        await context.send(f"Event alert channel is set to {channel.mention}")
    
    @alerts.error
    async def permissions_or_channel_fail(self, context: commands.Context, error: commands.errors.CommandError):
        if isinstance(error, commands.errors.MissingPermissions):
            await context.send("User needs Manage Server permission to use this command.")
        elif isinstance(error, commands.errors.ChannelNotFound):
            await context.send("Channel not found. Try again.")

    @staticmethod
    async def get_event_creator(event: discord.ScheduledEvent):
        fetched_event = await event.guild.fetch_scheduled_event(event.id)
        return await fetched_event.guild.fetch_member(fetched_event.creator.id)

    @staticmethod
    def get_role_from_event(event: discord.ScheduledEvent) -> discord.Role:
        for role in event.guild.roles:
            if EventAlerts.matches_role(event, role):                
                return role
        return None

    @staticmethod
    def get_channel_from_role(channel: discord.TextChannel | discord.ForumChannel, role: discord.Role) -> discord.TextChannel | discord.Thread:
        if isinstance(channel, discord.ForumChannel):
            for thread in channel.threads:
                if EventAlerts.matches_role(thread, role):
                    return thread
        else:
            if EventAlerts.matches_role(channel, role):
                return channel
        return None

    @staticmethod
    def matches_role(channel: discord.TextChannel | discord.Thread | discord.ScheduledEvent, role: discord.Role) -> bool:
        return " ping" in role.name.lower() and role.name.lower().replace(" ping", "") in channel.name.lower()