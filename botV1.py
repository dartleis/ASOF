# These are the necessary libaries required for the bot to run
import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
from asyncio import Queue
from datetime import datetime, timedelta
import subprocess
import re
import sys

POINTS_FILE = "points.json"        # Defines the points file as points.json
VALUES_FILE = "values.json"        # Defines the values file as values.json
JSON_CLEANUP_INTERVAL = 12        # How often to check if members have left the server, in hours
REMOVE_AFTER_DAYS = 30        # How long to wait after a member has left the server to remove them from the points file, in days

# Defines ids for roles
booster_id = 1353100755338530889    # test id, does not correlate to ASOF server role ids
#booster_id = 1385279332049485935
logistics_id = 1353100755338530889    # test id
#logistics_id = 1383446002182262856
#logistics_chief_id = "" 
contractofficer_id = 1353100755338530889    #test id
#contractofficer_id = 1406564078666649660

LOG_CHANNEL = 1427442431682543707

# Forwards logs to discord channel
class DiscordConsoleForwarder:
    def __init__(self, bot, channel_id, original_stream, buffer_time=3):
        self.bot = bot
        self.channel_id = channel_id
        self.original_stream = original_stream
        self.queue = Queue()
        self.buffer_time = buffer_time

    def write(self, message):
        self.original_stream.write(message)
        self.original_stream.flush()
        if "discord.app_commands.errors.CheckFailure" in message:
            return
        if message.strip():
            self.queue.put_nowait(message)

    def flush(self):
        self.original_stream.flush()

    async def start_flusher(self):
        while True:
            await asyncio.sleep(self.buffer_time)
            if not self.queue.empty():
                msgs = []
                while not self.queue.empty():
                    msgs.append(await self.queue.get())
                channel = self.bot.get_channel(self.channel_id)
                if channel:
                    text = "".join(msgs)
                    if len(text) > 1900:
                        text = text[:1900] + "..."
                    await channel.send(f"```\n{text}\n```")
def get_fastfetch():
    result = subprocess.run("fastfetch", shell=True, capture_output=True, text=True)
    output = result.stdout

    # Strip ANSI codes
    output = re.sub(r'\x1B\[[0-?]*[ -/]*[@-~]', '', output)

    # Redact the Local IP line
    output = re.sub(r'^Local IP.*$', 'Local IP (wlan0): REDACTED', output, flags=re.MULTILINE)

    # Insert a newline after the ASCII logo (before the 'pi@raspberrypi' line)
    output = output.replace('pi@raspberrypi', '\npi@raspberrypi', 1)

    return output

def tidy_number(num):        # Automatically cleans up numbers ending in .0
    if isinstance(num, float) and num.is_integer():
        return int(num)
    return num

def logistics_check():
    async def predicate(interaction: discord.Interaction) -> bool:
        member = interaction.user
        if member and discord.utils.get(member.roles, id=logistics_id):
            return True
        await interaction.response.send_message(
            "Sorry! You must be in the Logistics Department to use this command.",
            ephemeral=True
        )
        return False
    return app_commands.check(predicate)
    
def load_points():
    if not os.path.exists(POINTS_FILE):
        with open(POINTS_FILE, "w") as f:
            json.dump({}, f)
    with open(POINTS_FILE, "r") as f:
        data = json.load(f)
    
    for user_id, info in data.items():
        info["points"] = tidy_number(info.get("points", 0))
    
    return data

def save_points(data):
    for user_id, info in data.items():
        info["points"] = tidy_number(info.get("points", 0))
    with open(POINTS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_values():
    if not os.path.exists(VALUES_FILE):
        with open(VALUES_FILE, "w") as f:
            json.dump(
                {"ad": 0,
                 "adX3": 0,
                 "recruitment": 0,
                 "recruitmentsession": 0,
                 "rally": 0,
                 "rallyX5": 0,
                 "patrol": 0,
                 "gamenight": 0,
                 "training": 0,
                 "raid": 0,
                 "hosting": 0,
                 "cohosting": 0,
                 "booster": 0,
                 "joint": 0,
                 "eventlogging": 0,
                 "contractpayment": 0,
                 "nameplate": 0,
                 "basecommander": 0,
                 "bank": 0,
                 "goldbar": 0,
                 "trainee": 0,
                 "visitortransport": 0,
                 "pizzadelivery": 0}, f, indent=4)
    with open(VALUES_FILE, "r") as f:
        data = json.load(f)
    
    for key in data:
        data[key] = tidy_number(data[key])
    
    return data

def save_values(data):
    for key in data:
        data[key] = tidy_number(data[key])
    with open(VALUES_FILE, "w") as f:
        json.dump(data, f, indent=4)

def manual_cleanup_inactive_users():
    points_data = load_points()
    now = datetime.utcnow()
    removed = []

    for user_id, info in list(points_data.items()):
        if "last_seen" in info:
            last_seen = datetime.fromisoformat(info["last_seen"])
            if (now - last_seen) > timedelta(days=REMOVE_AFTER_DAYS):
                removed.append(user_id)
                del points_data[user_id]

    if removed:
        print(f"Removed inactive users: {removed}")
        save_points(points_data)

def get_points(user_id: int):        # Defines the get points function
    data = load_points()
    return data.get(str(user_id), {}).get("points", 0)

def add_points(user_id: int, amount: int):        # Defines the add points function
    data = load_points()
    user_id_str = str(user_id)

    if user_id_str not in data:
        data[user_id_str] = {"points": 0, "left_at": None}

    data[user_id_str]["points"] += amount
    save_points(data)

def set_points(user_id: int, amount: int):        
    data = load_points()
    user_id_str = str(user_id)
    
    if user_id_str not in data:
        data[user_id_str] = {"points": 0, "left_at": None}

    data[user_id_str] ["points"] = amount
    save_points(data)

def set_values(type: str, value: float):
    data = load_values()
    data[type.replace(" ", "")] = value
    save_values(data)

def get_value(key: str):
    data = load_values()
    return data.get(key, 0)

# Create a bot instance
intents = discord.Intents.default()
intents.message_content = True        # Allow the bot to read message content
intents.members = True        # Allows the bot to track who is in the server
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)
points_group = app_commands.Group(name="points", description="EXP system")
log_group = app_commands.Group(name="log", description="Used for logging things like events, ads, etc")
bot.tree.add_command(points_group)
bot.tree.add_command(log_group)


# Adds new members to points.json
@bot.event
async def on_member_join(member):
    data = load_points()
    if str(member.id) not in data:
        data[str(member.id)] = {"points": 0, "left_at": None}
        save_points(data)
        print(f"Added new member to points.json: {member.name}")

# Removes members from points.json after leaving
@bot.event
async def on_member_remove(member):
    data = load_points()
    if str(member.id) in data:
        data[str(member.id)]["left_at"] = datetime.now().isoformat()
        save_points(data)
        print(f"Marked {member.name} as left at {datetime.now().isoformat()}")

@tasks.loop(hours=JSON_CLEANUP_INTERVAL)
async def cleanup_inactive_users():
    manual_cleanup_inactive_users()
    data = load_points()
    now = datetime.now() 
    removed = 0

    for uid, info in list(data.items()):
        if info.get("left_at"):
            left_time = datetime.fromisoformat(info["left_at"])
            if now - left_time > timedelta(days=REMOVE_AFTER_DAYS):
                del data[uid]
                removed += 1

    if removed > 0:
        save_points(data)
        print(f"Removed {removed} users inactive for over {REMOVE_AFTER_DAYS} days.")

async def add_all_members(guild):
    points_data = load_points()
    added = 0

    for member in guild.members:
        # Skip bot accounts
        if member.bot:
            continue

        user_id = str(member.id)
        if user_id not in points_data:
            points_data[user_id] = {
                "points": 0,
                "last_seen": datetime.utcnow().isoformat(),
                "left_at": None
            }
            added += 1

        await asyncio.sleep(0.1)  # Adds a small delay when adding members to prevent hitting Discord rate limits, in seconds. 0.1 = 10 members per second
        print(f"Added {member.name} to points.json")

    save_points(points_data)
    print(f"Added {added} existing members to the database from {guild.name}")

@bot.event
async def on_ready():
    global stdout_forwarder, stderr_forwarder
    stdout_forwarder = DiscordConsoleForwarder(bot, LOG_CHANNEL, sys.__stdout__)
    stderr_forwarder = DiscordConsoleForwarder(bot, LOG_CHANNEL, sys.__stderr__)

    sys.stdout = stdout_forwarder
    sys.stderr = stderr_forwarder

    # Start flusher tasks
    bot.loop.create_task(stdout_forwarder.start_flusher())
    bot.loop.create_task(stderr_forwarder.start_flusher())

    print("Console forwarding to Discord is now active.")
    print(get_fastfetch())
    print(f"Logged in successfully as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")

    for guild in bot.guilds:
        print(f"Checking members in: {guild.name}")
        await add_all_members(guild)

    if not cleanup_inactive_users.is_running():
        cleanup_inactive_users.start()
        


# Code for /ping
@bot.tree.command(name="ping", description="Gets the ping of the bot. Mainly used for debug purposes.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f' Pong! {round (bot.latency * 1000)} ms', ephemeral=True)

# Code for /fastfetch
@bot.tree.command(name="fastfetch", description="fastfetch")
async def fastfetch(interaction: discord.Interaction):
    output = get_fastfetch()
    await interaction.response.send_message(f"```\n{get_fastfetch()}\n```", ephemeral=False)


# Code for /config
@bot.tree.command(name="config", description="configures the points values of different actions")
@logistics_check()
@app_commands.describe(type="What action to edit the values for", value="What to set the value to")
@app_commands.choices(type=[
    app_commands.Choice(name="ad", value="ad"),
    app_commands.Choice(name="ad x3", value="adX3"),
    app_commands.Choice(name="recruitment", value="recruitment"),
    app_commands.Choice(name="recruitment session", value="recruitmentsession"),
    app_commands.Choice(name="rally", value="rally"),
    app_commands.Choice(name="rally with over 5 people", value="rallyX5"),
    app_commands.Choice(name="patrol", value="patrol"),
    app_commands.Choice(name="gamenight", value="gamenight"),
    app_commands.Choice(name="training", value="training"),
    app_commands.Choice(name="raid", value="raid"),
    app_commands.Choice(name="event hosting", value="hosting"),
    app_commands.Choice(name="event co-hosting", value="cohosting"),
    app_commands.Choice(name="server booster event bonus", value="booster"),
    app_commands.Choice(name="joint event with other divisions bonus", value="joint"),
    app_commands.Choice(name="logistics event logging", value="eventlogging"),
    app_commands.Choice(name="contract officer completed payment", value="contractpayment"),
    app_commands.Choice(name="nameplate order completed", value="nameplate"),
    app_commands.Choice(name="leaderboard base commander kill", value="basecommander"),
    app_commands.Choice(name="leaderboard bank robbery completed", value="bank"),
    app_commands.Choice(name="leaderboard gold bar stolen", value="goldbar"),
    app_commands.Choice(name="leaderboard trainee trained", value="trainee"),
    app_commands.Choice(name="leaderboard visitor transported", value="visitortransport"),
    app_commands.Choice(name="leaderboard pizza delivered", value="pizzadelivery")])
async def config(interaction: discord.Interaction, type: app_commands.Choice[str], value: float):
    set_values(type.value, value)
    await interaction.response.send_message(f"Set value of **{type.value}** to **{get_value(type.value)}**")

# /points check command
@points_group.command(name="check", description="Check the points of you or another member")
@app_commands.describe(user="User to check (optional)")
async def check(interaction: discord.Interaction, user: discord.User = None):
    target = user or interaction.user
    points = get_points(target.id)
    if points >= 1000:
        await interaction.response.send_message(f"🤑 **{target.display_name}** has **{points}** points.")
    elif points == 100:
        await interaction.response.send_message(f"💯 **{target.display_name}** has **{points}** points.")
    else:
        await interaction.response.send_message(f"**{target.display_name}** has **{points}** points.")

# /points add command
@points_group.command(name="add", description="Add points to a user")
@logistics_check()
@app_commands.describe(user="User to add points to", amount="How many points to add")
async def add(interaction: discord.Interaction, user: discord.User, amount: float):
    add_points(user.id, amount)
    amount = tidy_number(amount)
    await interaction.response.send_message(f"Added **{amount}** points to **{user.display_name}**, bringing their total to **{get_points(user.id)}**.")
    
# /points subtract command
@points_group.command(name="subtract", description="Remove points from a user")
@logistics_check()
@app_commands.describe(user="User to remove points from", amount="How many points to remove")
async def subtract(interaction: discord.Interaction, user: discord.User, amount: float):
    add_points(user.id, -abs(amount))
    amount = tidy_number(amount)
    await interaction.response.send_message(f"Removed **{abs(amount)}** points from **{user.display_name}**, bringing their total to **{get_points(user.id)}**.")

# /points set command
@points_group.command(name="set", description="Set the points of a user")
@logistics_check()
@app_commands.describe(user="User to set the points of", amount="Amount of points to set")
async def set(interaction: discord.Interaction, user: discord.User, amount: float):
    set_points(user.id, amount)
    amount = tidy_number(amount)
    await interaction.response.send_message(f"Set the points of **{user.display_name}** to **{amount}**")

# /log event
@log_group.command(name="event", description="Log the points for someone attending/hosting an event")
@logistics_check()
@app_commands.describe(
    user="User who attended/hosted the event",
    event_type="What type of event",
    attendance_type="How did they attend the event? (Attending, Hosting or Co-hosting)"
)
@app_commands.choices(event_type=[
    app_commands.Choice(name="Patrol", value="patrol"),
    app_commands.Choice(name="Gamenight", value="gamenight"),
    app_commands.Choice(name="Training", value="training"),
    app_commands.Choice(name="Raid", value="raid"),
    app_commands.Choice(name="Recruitment Session", value="recruitmentsession")
])
@app_commands.choices(attendance_type=[
    app_commands.Choice(name="Attending", value="attending"),
    app_commands.Choice(name="Co Hosting", value="cohosting"),
    app_commands.Choice(name="Hosting", value="hosting")
])
async def event(interaction: discord.Interaction, user: discord.User, event_type: app_commands.Choice[str], attendance_type: app_commands.Choice[str]): 
    
# Attendance types
    if attendance_type.value == "attending":
        added = get_value(event_type.value)
    else:
        added = get_value(event_type.value) + get_value(attendance_type.value)
    
    member = interaction.guild.get_member(user.id)

    booster_bonus = 0
    if member and discord.utils.get(member.roles, id=booster_id):
        booster_bonus = get_value("booster")
        added += booster_bonus
    add_points(user.id, added)
    msg = (f"Added **{added}** points to **{user.display_name}** for {attendance_type.name.lower().replace(" ", "-")} a **{event_type.name}**.")

    if booster_bonus > 0:        # Checks if member is a server booster
            msg += f"\n<:booster_icon:1425732545986822164> That includes an extra **{booster_bonus}** points for being a **Server Booster**! Thank you for supporting the division!"

    msg += f"\nThey now have **{get_points(user.id)}** points."

    await interaction.response.send_message(msg)

# /log recruitment command
@log_group.command(name="recruitment", description="Log the points for someone recruiting a member in the Discord")
@logistics_check()
@app_commands.describe(user="User who recruited someone", amount="How many people were recruited (Optional)")
async def recruitment(interaction: discord.Interaction, user: discord.User, amount: int = 1):
    added = get_value("recruitment") * amount
    add_points(user.id, added)
    await interaction.response.send_message(
    f"Added **{added}** points to **{user.display_name}** for **recruiting** **{amount}** members.\n"
    f" They now have **{get_points(user.id)}** points.")

# /log rally command
@log_group.command(name="rally", description="Log the points for someone attending the weekly rally")
@logistics_check()
@app_commands.describe(user="User who attended the rally", amount_attendees="Amount of total attendees were at the rally", rally="Which rally was attended")
@app_commands.choices(rally=[
    app_commands.Choice(name="1 AM rally", value="1am"),
    app_commands.Choice(name="1 PM rally", value="1pm")])
async def rally(interaction:discord.Interaction, user: discord.User, amount_attendees: int, rally: app_commands.Choice[str]):
    if amount_attendees >= 5:
        added = get_value("rallyX5")
    else:
        added = get_value("rally")
    add_points(user.id, added)
    await interaction.response.send_message(
        f"Added **{added}** points to **{user.display_name}** for representing ASOF at the **{rally.name}** with {str(amount_attendees - 1).replace("-1", "0")} others"
        f"\nThey now have **{get_points(user.id)}** points"
    )

# /log leaderboard command
@log_group.command(name="leaderboard", description="Log the points for someone completing leaderboard tasks")
@logistics_check()
@app_commands.describe(user="User who completed the leaderboard task", task="Which leaderboard task was completed", amount="How many times was the task completed")
@app_commands.choices(task=[
    app_commands.Choice(name="Visitor Transportation", value="visitortransport"),
    app_commands.Choice(name="Pizza Delivery", value="pizzadelivery"),
    app_commands.Choice(name="Bank Robbery", value="bank"),
    app_commands.Choice(name="Gold Bar Stolen", value="goldbar"),
    app_commands.Choice(name="Trainee Trained", value="trainee"),
    app_commands.Choice(name="Base Commander Elimination", value="basecommander")])
async def leaderboard(interaction: discord.Interaction, user: discord.User, task: app_commands.Choice[str], amount: int = 1):
    added = get_value(task.value * amount)
    add_points(user.id, added)
    msg = f"Added **{added}** points to **{user.name}** for "
    if task.value == "visitortransport":
        msg += f"transporting **{amount}** visitor{"s" if amount > 1 else ""}"
    elif task.value == "pizzadelivery":
        msg += f"delivering **{amount}** pizza{"s" if amount > 1 else ""}"
    elif task.value == "bank":
        msg += f"robbing **{amount}** bank{"s" if amount > 1 else ""}"
    elif task.value == "goldbar":
        msg += f"stealing **{amount}** gold bar{"s" if amount > 1 else ""}"
    elif task.value == "trainee":
        msg += f"training **{amount}** trainee{"s" if amount > 1 else ""}"
    else:
        msg += f"Eliminating **{amount}** Base Commander{"s" if amount > 1 else ""}"
    await interaction.response.send_message(msg)

# Autocomplete function for /leaderboard
async def leaderboard_page_autocomplete(interaction: discord.Interaction, current: str):
    points_data = load_points()
    per_page = 10
    total_pages = (len(points_data) + per_page - 1) // per_page or 1

    suggestions = [app_commands.Choice(name=str(i), value=str(i)) for i in range(1, total_pages + 1)]
    suggestions.append(app_commands.Choice(name="all", value="all"))

    return [s for s in suggestions if current.lower() in s.name.lower()]

# /leaderboard command
@bot.tree.command(name="leaderboard", description="Shows how many points people have on a leaderboard")
@app_commands.describe(page="Select a page number or 'all'")
@app_commands.autocomplete(page=leaderboard_page_autocomplete)
async def leaderboard(interaction: discord.Interaction, page: str):
    points_data = load_points()
    guild = interaction.guild
    members = {str(m.id): m for m in guild.members if not m.bot}

    leaderboard_list = [
        (int(uid), info.get("points", 0))
        for uid, info in points_data.items()
        if uid in members
    ]
    leaderboard_list.sort(key=lambda x: x[1], reverse=True)

    if len(leaderboard_list) == 0:
        await interaction.response.send_message("No one is on the leaderboard yet.")
        return

    per_page = 10
    total_pages = (len(leaderboard_list) + per_page - 1) // per_page

    # If "all" is chosen
    if page.lower() == "all":
        display_list = leaderboard_list
        ephemeral = True
        page_num = 1
    else:
        try:
            page_num = int(page)
            if page_num < 1 or page_num > total_pages:
                await interaction.response.send_message(f"Invalid page number. There {f"are only **{total_pages}** pages" if total_pages > 1 else f"is only **1** page"}.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message(f"Page must be {f" a number (1 to {total_pages})" if total_pages > 1 else "1"} or `all`.", ephemeral=True)
            return

        start_index = (page_num - 1) * per_page
        end_index = start_index + per_page
        display_list = leaderboard_list[start_index:end_index]
        ephemeral = False

    # Build leaderboard text
    lines = []
    rank_offset = 0 if page.lower() == "all" else (per_page * (page_num - 1))
    for rank, (user_id, points) in enumerate(display_list, start=1 + rank_offset):
        member = members.get(str(user_id))
        name = member.display_name if member else f"Unknown User ({user_id})"
        points_display = int(points) if float(points).is_integer() else points
        lines.append(f"**#{rank}** — {name}: {points_display} points")

    # Title
    if page.lower() == "all":
        title = f"🏆 Full Leaderboard — {len(leaderboard_list)} players"
    else:
        title = f"🏆 Leaderboard — Page {page_num}/{total_pages}"

    await interaction.response.send_message(
        f"{title}\n" + "\n".join(lines),
        ephemeral=ephemeral
    )

# Runs the bot with the bot token
with open("token.txt", "r") as file:        # Imports the Discord bot token from a secure external file
    token = file.read().strip()

bot.run(token)
