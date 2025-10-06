# These are the necessary libaries required for the bot to run
import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
import asyncio
from datetime import datetime, timedelta

# Config
POINTS_FILE = "points.json"        # Defines the points file as points.json
JSON_CLEANUP_INTERVAL = 12        # How often to check if members have left the server, in hours
REMOVE_AFTER_DAYS = 30        # How long to wait after a member has left the server to clear their points, useful if a member accidentally left or if they lost their account and require their points to be transferred over

# Defines functions related to the points system
def load_points():        # Defines the load points function
    if not os.path.exists(POINTS_FILE):
        with open(POINTS_FILE, "w") as f:
            json.dump({}, f)
    with open(POINTS_FILE, "r") as f:
        return json.load(f)

def save_points(data):        # Defines the save points function
    with open(POINTS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_points(user_id: int):        # Defines the get points function
    data = load_points()
    return data.get(str(user_id), 0)

def add_points(user_id: int, amount: int):        # Defines the add points function
    data = load_points()
    data[str(user_id)] = data.get(str(user_id), 0) + amount
    save_points(data)

# Create a bot instance
intents = discord.Intents.default()
intents.message_content = True        # Allow the bot to read message content
intents.members = True        # Allows the bot to track member joins/leaves, essential for automatically adding/removing users from the points file
bot = commands.Bot(command_prefix="!", intents=intents)

# Syncs slash commands and prints any exceptions (errors) on startup to the console
@bot.event
async def on_ready():
    print(f"Logged in successfully as {bot.user}")
    try:
        synced = await bot.tree.sync()        # Sync slash commands
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# Code for /ping
@bot.tree.command(name="ping", description="Gets the ping of the bot. Mainly used for debug purposes.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f' Pong! {round (bot.latency * 1000)} ms')

# Code for /points_check
@bot.tree.command(name="points_check", description="Check your or another user's points")
@app_commands.describe(user="The user to check (optional)")
async def points_check(interaction: discord.Interaction, user: discord.User = None):
    target = user or interaction.user
    points = get_points(target.id)
    await interaction.response.send_message(f"💰 **{target.display_name}** has **{points}** points.", ephemeral=True)

# Code for /points_add
@bot.tree.command(name="points_add", description="Add points to a user")
@app_commands.describe(user="The user to add points to", amount="How many points to add")
async def points_add(interaction: discord.Interaction, user: discord.User, amount: int):

    add_points(user.id, amount)
    await interaction.response.send_message(f"✅ Added **{amount}** points to **{user.display_name}**!", ephemeral=True)



with open("token.txt", "r") as file:        # Imports my Discord bot token from an external file (The bot token is very important, so that is why it is hidden and not listed here)
    token = file.read().strip()

bot.run(token)
