import asyncio, datetime, discord, os, re

from discord.ext import commands
from dotenv import load_dotenv
from ioutils import read, write
from typing import Optional

load_dotenv()
token = os.getenv("TOKEN")

command_prefix = os.getenv("PREFIX")
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!" if command_prefix is None else command_prefix, intents=intents)


## COPYPASTA ##
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return
    copypastas = read("copypastas.json")
    for phrase in copypastas:
        if phrase in message.content.lower():
            await message.channel.send(copypastas[phrase])
    await bot.process_commands(message)


## ALERTS ##
@bot.event
async def on_scheduled_event_create(event: discord.ScheduledEvent):
    for role in event.guild.roles:
        if role.name.replace(" Ping", "") in event.name:
            channel = await event.guild.fetch_channel(read("settings.json", event.guild.id, "scheduled_event_alert_channel_id"))
            start_time = int(event.start_time.timestamp())
            await channel.send(f"{event.name} is set for <t:{start_time}>! {role.mention}")

@bot.command()
async def alerts(context: commands.Context, argument: str):
    print("starting alerts")
    if context.message.author.guild_permissions.manage_guild:
        for channel in context.guild.channels:
            if argument in [channel.name, channel.mention]:
                write("settings.json", channel.id, context.guild.id, "scheduled_event_alert_channel_id")
                await context.send(f"Event alert channel is set to {channel.mention}")
                return
        await context.send("Channel not found. Try again.")
        return
    await context.send("User needs Manage Server permission to use this command.")
    return


## STREAMPAUSE ##
streampause_data: dict[discord.Message, discord.Member] = None

@bot.event
async def on_reaction_add(reaction: discord.Reaction, user: discord.Member):
    global streampause_data
    if streampause_data is not None:
        await attempt_to_finish_streampause(reaction, user, user.voice.channel if user.voice else None)

@bot.event
async def on_voice_state_update(member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    global streampause_data
    if streampause_data is not None:
        voice_channel = before.channel if after.channel is None else after.channel if before.channel is None else None
        reaction = discord.utils.get(streampause_data["message"].reactions, emoji="👍")

        await attempt_to_finish_streampause(reaction, member, voice_channel)

@bot.command()
async def streampause(context: commands.Context):
    if context.author.voice is None:
        message = await context.send("This command is only usable inside a voice channel.")
        await message.delete(delay=5.0)
        return

    message = await context.send("React with 👍 when you're all set!")

    global streampause_data
    streampause_data = {
        "message": message,
        "author": context.author
    }

    await message.add_reaction("👍")

async def attempt_to_finish_streampause(reaction: discord.Reaction, user: discord.Member, voice_channel: Optional[discord.VoiceChannel]):
    global streampause_data
    if user.bot or reaction.message != streampause_data["message"] or reaction.emoji != "👍" or voice_channel is None:
        return

    reacted_members = set(await reaction.users().flatten())
    vc_members = set(voice_channel.members)

    if reacted_members & vc_members == vc_members:
        original_author = streampause_data["author"]
        await reaction.message.channel.send(f"{original_author.mention} Everyone's here!")

        await reaction.message.delete()
        streampause_data = None


## REMINDME ##
@bot.event
async def on_ready():
    for guild in bot.guilds:
        for file in ["settings.json", "reminders.json"]:
            if read(file, guild.id) is None:
                write(file, {}, guild.id)
        reminders_list = map(tuple, read("reminders.json", guild.id))
        reminders = set(reminders_list if reminders_list is not None else [])
        for reminder in reminders:
            reminder = (await bot.fetch_user(reminder[0]), await bot.fetch_channel(reminder[1]), *reminder[2:])
            await process_reminder(*reminder, None)

@bot.command()
async def remindme(context: commands.Context, time: str, reminder: str):
    # Determine the amount of time based on the time inputted
    timer_parameters = re.fullmatch("(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", time)
    if timer_parameters is None:
        timer_parameters = re.search("(?:(\d+)d)?(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", time)
        num_days, num_hours, num_minutes, num_seconds = tuple(map(lambda t: int(0 if t is None else t), timer_parameters.groups()))
        
        correct_time_string = re.sub("0.", "", f"{num_days}d{num_hours}h{num_minutes}m{num_seconds}s")
        await context.send(f"Time string is not formatted correctly; did you mean to type {correct_time_string}?")
        return

    num_days, num_hours, num_minutes, num_seconds = tuple(map(lambda t: int(0 if t is None else t), timer_parameters.groups()))

    date_time = datetime.datetime.now() + datetime.timedelta(days = num_days, hours = num_hours, minutes = num_minutes, seconds = num_seconds)
    timestamp = int(round(date_time.timestamp()))

    await process_reminder(context.message.author, context.message.channel, timestamp, reminder, context.message)

async def process_reminder(author: discord.Member, channel: discord.TextChannel, timestamp: int, reminder: str, command_message: Optional[discord.Message]):
    # Add the new reminder to the list of reminders and write the updated list into settings.json
    reminders_list = map(tuple, read("reminders.json", channel.guild.id))
    reminders = set(reminders_list if reminders_list is not None else [])
    
    reminders.add((author.id, channel.id, timestamp, reminder))
    write("reminders.json", list(reminders), channel.guild.id)

    if command_message:
        await command_message.add_reaction("👍")

    # Wait until the correct time, send a message to remind the user, and remove the reminder from the list
    sleep_time = timestamp - int(round(datetime.datetime.now().timestamp()))
    if sleep_time > 0:
        await asyncio.sleep(sleep_time)
    await command_message.reply(f"{author.mention} {reminder}")

    reminders.remove((author.id, channel.id, timestamp, reminder))
    write("reminders.json", list(reminders), channel.guild.id)


bot.run(token)