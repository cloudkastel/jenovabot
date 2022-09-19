import datetime, json, re
from dataclasses import dataclass
from ioutils import read_sql, write_sql

import discord
from discord.ext import commands, tasks


@dataclass(frozen=True)
class Reminder:
    """Data associated with a scheduled reminder."""

    command_message: discord.Message
    reminder_datetime: datetime.datetime
    reminder_str: str

    def __str__(self):
        return f"Reminder in {self.command_message.channel.mention} by {self.command_message.author.name} for <t:{int(self.reminder_datetime.timestamp())}>: {self.reminder_str!r}"

    def __repr__(self):
        return f"{self.command_message.author.name} - #{self.command_message.channel.name} @ {self.reminder_datetime.strftime('%a %b %d, %I:%M %p')}: {self.reminder_str!r}"

    def to_json(self) -> str:
        """Covnert the current reminder object to a JSON string."""

        json_obj = {
            "channel_id": self.command_message.channel.id,
            "command_message_id": self.command_message.id,
            "reminder_timestamp": self.reminder_datetime.timestamp(),
            "reminder_str": self.reminder_str
        }
        return json.dumps(json_obj)

    @staticmethod
    async def from_json(bot: commands.Bot, json_obj: dict[str, int | float | str]):
        """Convert a JSON dictionary to a Reminder object."""

        channel = bot.get_channel(json_obj["channel_id"])

        command_message = await channel.fetch_message(json_obj["command_message_id"])
        reminder_datetime = datetime.datetime.fromtimestamp(json_obj["reminder_timestamp"])
        reminder_str = json_obj["reminder_str"]

        return Reminder(command_message, reminder_datetime, reminder_str)

class ReminderCancelSelect(discord.ui.Select):
    def __init__(self, context: commands.Context, reminders: set[Reminder]):
        self.bot = context.bot
        self.reminders = reminders

        options = [discord.SelectOption(label=repr(reminder)) for reminder in reminders]
        super().__init__(placeholder="Select reminders to cancel...", max_values=len(reminders), options=options)
    
    async def callback(self, interaction: discord.Interaction):
        cancelled_reminders = {reminder for reminder in self.reminders if repr(reminder) in self.values}
        self.bot.get_cog("Reminders").reminders[interaction.guild_id] -= cancelled_reminders

        await interaction.response.send_message(f"Cancelled: {[str(reminder) for reminder in cancelled_reminders]}", ephemeral=True)

class ReminderCancelView(discord.ui.View):
    def __init__(self, context: commands.Context, reminders: set[Reminder]):
        super().__init__()
        self.add_item(ReminderCancelSelect(context, reminders))
    
    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user == self.member

class Reminders(commands.Cog, name="Reminders"):
    """Create and send scheduled reminder messages."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminders: dict[int, set[Reminder]] = {}
    
    @commands.Cog.listener()
    async def on_ready(self):
        """Initialize the reminders instance dictionary from SQL data and start the reminder processing loop."""

        for guild in self.bot.guilds:
            if read_sql("reminders", guild.id, "reminders") is None:
                write_sql("reminders", guild.id, "reminders", "array[[]]::json[]")
            self.reminders[guild.id] = {await Reminder.from_json(self.bot, json_str) for json_str in read_sql("reminders", guild.id, "reminders")}
        
        self._cached_reminders = self.reminders.copy()
        self.send_reminders.start()
        self.sync_sql.start()
 
    @commands.group(aliases=["remindme", "rm"], invoke_without_command=True)
    async def remind(self, context: commands.Context, time: str, *, reminder_str: str = ""):
        """Set a scheduled reminder. Format time as: _d_h_m_s (may omit individual parameters)"""

        # Determine the amount of time based on the time inputted
        num_days, num_hours, num_minutes, num_seconds, is_valid = Reminders.get_datetime_parameters(time)
        if not is_valid:
            time_string_guess = re.sub("0.", "", f"{num_days}d{num_hours}h{num_minutes}m{num_seconds}s")
            if time_string_guess == "":
                await context.send(f"Time string is not formatted correctly; not sure what you meant to type here.")
            else:
                await context.send(f"Time string is not formatted correctly; did you mean to type {time_string_guess}?")
            return
        reminder_datetime = datetime.datetime.now() + datetime.timedelta(days = num_days, hours = num_hours, minutes = num_minutes, seconds = num_seconds)

        reminder = Reminder(context.message, reminder_datetime, reminder_str)
        
        if context.guild.id not in self.reminders:
            self.reminders[context.guild.id] = set()
        self.reminders[context.guild.id].add(reminder)
        
        await context.message.add_reaction("👍")
    
    @staticmethod
    def get_datetime_parameters(time: str):
        """Convert a time string into parameters for a datetime object."""

        is_valid = True

        timer_parameters = re.fullmatch("(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", time)
        if timer_parameters is None:
            timer_parameters = re.search("(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", time)
            is_valid = False
        
        return (*tuple(map(lambda t: int(0 if t is None else t), timer_parameters.groups())), is_valid)

    @remind.command()
    async def viewall(self, context: commands.Context):
        """View scheduled reminders of every server member."""
        
        if len(self.reminders[context.guild.id]) == 0:
            await context.send("No reminders currently set.")
            return

        reminder_list = discord.Embed()
        for i, reminder in enumerate(self.reminders[context.guild.id]):
            reminder_list.add_field(name=f"{i+1}.", value=reminder, inline=False)
        await context.send(embed=reminder_list)

    @remind.command()
    async def cancel(self, context: commands.Context):
        """Cancel scheduled reminders."""
        
        is_viewable = lambda reminder: context.author.guild_permissions.manage_guild or reminder.command_message.author == context.author
        filtered_reminders = {reminder for reminder in self.reminders[context.guild.id] if is_viewable(reminder)}
        
        if len(filtered_reminders) == 0:
            await context.send("No reminders currently set.")
            return

        await context.send(view=ReminderCancelView(context, filtered_reminders))
    
    @tasks.loop(seconds=0.2)
    async def send_reminders(self):
        """Send any reminders past their scheduled date."""

        for guild in self.bot.guilds:
            reminders = self.reminders[guild.id].copy()
            for reminder in reminders:
                if reminder.reminder_datetime <= datetime.datetime.now():
                    await reminder.command_message.reply(reminder.reminder_str)
                    self.reminders[guild.id].remove(reminder)
    
    @tasks.loop(seconds=0.3)
    async def sync_sql(self):
        """Sync with the SQL database if any changes are detected."""

        for guild in self.bot.guilds:
            if self.reminders[guild.id] != self._cached_reminders[guild.id]:
                write_sql("reminders", guild.id, "reminders", f"array{[reminder.to_json() for reminder in self.reminders[guild.id]]}::json[]")
                self._cached_reminders = self.reminders.copy()