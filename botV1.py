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
@bot.tree.command(name="hello", description="Say hello to the bot!")
async def hello(interaction: discord.Interaction):
    await interaction.response.send_message(f"👋 Hello, {interaction.user.display_name}!")

# Import the token
# You really think i'm dumb enough to leave my bot token in a public repo
with open("token.txt", "r") as file:
    token = file.read()

# Run the bot
bot.run(token)
