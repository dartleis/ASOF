# These are the necessary libaries required for the bot to run
import discord
from discord import app_commands
from discord.ext import commands, tasks
import json, os, asyncio
from datetime import datetime, timedelta

POINTS_FILE = "points.json"        # Defines the points file as points.json
VALUES_FILE = "values.json"        # Defines the values file as values.json
JSON_CLEANUP_INTERVAL = 12        # How often to check if members have left the server, in hours
REMOVE_AFTER_DAYS = 30        # How long to wait after a member has left the server to remove them from the points file, in days

def load_points():  
    if not os.path.exists(POINTS_FILE):
        with open(POINTS_FILE, "w") as f:
            json.dump({}, f)
    with open(POINTS_FILE, "r") as f:
        return json.load(f)

def save_points(data):      
    with open(POINTS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def load_values():
    if not os.path.exists(VALUES_FILE):
        with open(VALUES_FILE, "w") as f:
            json.dump({"ad": 0, "adX3": 0, "recruitment": 0, "recruitmentsession": 0, "rally": 0, "rallyX5": 0, "patrol": 0, "gamenight": 0, "training": 0, "raid": 0, "hosting": 0, "cohosting": 0, "booster": 0, "jointevent": 0, "eventlogging": 0, "contractpayment": 0, "nameplate": 0, "basecommander": 0, "bank": 0, "goldbar": 0, "trainee": 0, "visitortransport": 0, "pizzadelivery": 0}, f, indent=4) 
    with open(VALUES_FILE, "r") as f:
        return json.load(f)

def save_values(data):
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
        print(f"🧹 Removed inactive users: {removed}")
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

def get_value(type: str, value: float):
    data = load_values()
    return data.get(type, {}).get("value", 0)

# Create a bot instance
intents = discord.Intents.default()
intents.message_content = True        # Allow the bot to read message content
intents.members = True        # Allows the bot to track who is in the server
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)
points_group = app_commands.Group(name="points", description="EXP system")
log_group = app_commands.Group(name="log", description="Used for logging things like events, ads, etc")
leaderboard_group = app_commands.Group(name="leaderboard", description="Used by Leaderboard Officers to efficiently log points for leaderboard activity completions")
bot.tree.add_command(points_group)
bot.tree.add_command(log_group)
bot.tree.add_command(leaderboard_group)


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
    print(f"Logged in successfully as {bot.user}")
    try:
        synced = await bot.tree.sync()        # Sync slash commands
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
@app_commands.describe(user="User to add points to", amount="How many points to add")
async def add(interaction: discord.Interaction, user: discord.User, amount: int):
    add_points(user.id, amount)
    await interaction.response.send_message(f"Added **{amount}** points to **{user.display_name}**, bringing their total to **{get_points(user.id)}**.")

# /points subtract command
@points_group.command(name="subtract", description="Remove points from a user")
@app_commands.describe(user="User to remove points from", amount="How many points to remove")
async def subtract(interaction: discord.Interaction, user: discord.User, amount: int):
    add_points(user.id, -abs(amount))
    await interaction.response.send_message(f"Removed **{abs(amount)}** points from **{user.display_name}**, bringing their total to **{get_points(user.id)}**.")

# /points set command
@points_group.command(name="set", description="Set the points of a user")
@app_commands.describe(user="User to set the points of", amount="Amount of points to set")
async def set(interaction: discord.Interaction, user: discord.User, amount: int):
    set_points(user.id, amount)
    await interaction.response.send_message(f"Set the points of **{user.display_name}** to **{amount}**")

# /log patrol command    (to be improved with selection for host, cohost, all attendees etc, allowing one event to be logged with just one command)
@log_group.command(name="patrol", description="Log the points for someone attending/hosting a **Patrol**")
@app_commands.describe(user="User who attended/hosted the event", type="How did they attend the event? (Attending, Hosting or Co-hosting)")
@app_commands.choices(type=[
    app_commands.choice(name="Attending", value="attending"),
    app_commands.choice(name="Co Hosting", value="cohosting"),
    app_commands.choice(name="Hosting", value="hosting")])
async def patrol(interaction: discord.Interaction, user: discord.User, type: app_commands.Choice[str]):
    type: app_commands.choice[str],
        if type == attending:
            added = get_value(type=patrol)
            add_points(user.id, added)
        elif type == cohosting:
            added = sum(get_value(type=patrol), get_value(type=cohosting))
            add_points(user.id, added)
        elif type == hosting:
            added = sum(get_value(type=patrol), get_value(type=hosting))
            add_points(user.id, added)
    await interaction.response.send_message(f"Added {added} points to {user} for **{type}** a **patrol**. They now have **{get_points(user.id)}** points")

with open("token.txt", "r") as file:        # Imports the Discord bot token from a secure external file
    token = file.read().strip()

bot.run(token)
