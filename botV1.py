import discord
from discord import app_commands
from discord.ext import commands

# Create a bot instance
intents = discord.Intents.default()
intents.message_content = True  # Allow the bot to read message content
bot = commands.Bot(command_prefix="!", intents=intents)

# Event: When the bot is ready
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()  # Sync slash commands
        print(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# Define a slash command
@bot.tree.command(name="ping", description="Gets the ping of the bot. Mainly used for debug purposes.")
async def ping(ctx):
    await ctx.send(f'Pong! {round (bot.latency * 1000)} ms') # Fetches the ping and sends it as a message.

with open("token.txt", "r") as file: # Imports my Discord bot token from an external file (The bot token is very important, so that is why it is hidden and not listed here)
    token = file.read().strip()

# Run the bot
bot.run(token)
