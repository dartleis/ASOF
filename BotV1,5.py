"""
ASOF BOT V1.5 BETA
"""

"""
IMPORTS
"""

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
import json
import os
import asyncio
from google import genai
from google.genai import types
import re
import functools
import tomllib
from dotenv import load_dotenv

"""
CONSTANTS
"""



POINTS_FILE = "points.json"
CONFIG_FILE = "config.json"

"""
ROLES AND USER IDS
"""

logistics_id = 1383446002182262856
booster_id = 1385279332049485935

ALWAYS_PRIVILEGED_ROLE_IDS = []
ALWAYS_PRIVILEGED_USER_IDS = [805175554209873940]
PRIVILEGE_GROUP_ROLE_IDS = {
    "logistics": [logistics_id]
}

"""
UTILITY FUNCTIONS
"""

def tidy_number(num):
    return int(num) if isinstance(num, float) and num.is_integer() else num

def load_json(file, default):
    if not os.path.exists(file):
        with open(file, "w") as f:
            json.dump(default, f, indent=4)
    with open(file, "r") as f:
        data = json.load(f)
    return {
        k: tidy_number(v) if isinstance(v, (int, float)) else v for k, v in data.items()
    }


def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=4)


def privileged_check(group: str = None, target_param: str | list[str] = None):
    async def predicate(interaction: discord.Interaction) -> bool:
        allowed_roles = set(ALWAYS_PRIVILEGED_ROLE_IDS)
        if group in PRIVILEGE_GROUP_ROLE_IDS:
            allowed_roles.update(PRIVILEGE_GROUP_ROLE_IDS[group])

        def has_permission(member: discord.Member) -> bool:
            return member.id in ALWAYS_PRIVILEGED_USER_IDS or any(
                r.id in allowed_roles for r in member.roles
            )

        # Collect targets
        targets = []
        if target_param:
            names = [target_param] if isinstance(target_param, str) else target_param
            for name in names:
                target = getattr(interaction.namespace, name, None)
                if isinstance(target, discord.User):
                    target = interaction.guild.get_member(target.id)
                if isinstance(target, discord.Member):
                    targets.append(target)

        # Check executor
        executor = interaction.user
        if not has_permission(executor):
            await interaction.response.send_message(
                f"You ({executor.mention}) do not have permission to use this command.",
                ephemeral=True,
            )
            return False

        # Check targets
        for target in targets:
            if not has_permission(target):
                await interaction.response.send_message(
                    f"{target.mention} does not have the required role for this action.",
                    ephemeral=True,
                )
                return False
        return True

    return app_commands.check(predicate)

"""
POINTS AND CONFIG
"""

def load_points():
    data = load_json(POINTS_FILE, {})
    for uid, info in data.items():
        info["points"] = tidy_number(info.get("points", 0))
    return data


def save_points(data):
    for uid, info in data.items():
        info["points"] = tidy_number(info.get("points", 0))
    save_json(POINTS_FILE, data)

def load_values():
    default_values = {
        "ad": 0,
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
        "pizzadelivery": 0
    }
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump({"values": default_values, "ranks": {}}, f, indent=4)
    with open(CONFIG_FILE, "r") as f:
        data = json.load(f)
    if "values" not in data:
        data["values"] = default_values
    for key, val in default_values.items():
        if key not in data["values"]:
            data["values"][key] = val
    for key in data["values"]:
        data["values"][key] = tidy_number(data["values"][key])
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

    return data["values"]

def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump({"values": {}, "ranks": {}}, f, indent=4)
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

def get_value(key: str):
    return load_config()["values"].get(key, 0)

def load_ranks():
    return load_config().get("ranks", {})

"""
POINTS HELPERS
"""

def get_points(uid: int):
    return load_points().get(str(uid), {}).get("points", 0)


def add_points(uid: int, amount: int):
    data = load_points()
    entry = data.setdefault(str(uid), {"points": 0, "left_at": None})
    entry["points"] += amount
    save_points(data)


def set_points(uid: int, amount: int):
    data = load_points()
    entry = data.setdefault(str(uid), {"points": 0, "left_at": None})
    entry["points"] = amount
    save_points(data)

"""
CHECK FOR PROMOTIONS
"""

async def check_for_promotion(member: discord.Member):
    points = get_points(member.id)
    ranks = load_ranks()
    user_role_ids = [r.id for r in member.roles]

    sorted_ranks = sorted(
        ranks.items(),
        key=lambda x: x[1]["points_required"], reverse=True
    )

    current_highest_rank_points = 0
    for name, info in sorted_ranks:
        if info["role_id"] in user_role_ids:
            if info["points_required"] > current_highest_rank_points:
                current_highest_rank_points = info["points_required"]

    for name, info in sorted_ranks:
        required_points = info["points_required"]
        required_roles = info["requires_roles"]
        role_id = info["role_id"]

        if current_highest_rank_points > required_points:
            continue

        if (
            points >= required_points and
            all(rid in user_role_ids for rid in required_roles) and
            role_id not in user_role_ids
        ):
            return name

    return None

def promotion_check(_func=None, *, target_param: str = "user"):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            # Run the command logic — should return the base msg string
            base_msg = await func(interaction, *args, **kwargs)
            if not isinstance(base_msg, str):
                base_msg = ""

            # Get target user
            target = kwargs.get(target_param, None)
            if not target and len(args) > 0:
                target = args[0]

            if not isinstance(target, (discord.User, discord.Member)):
                await interaction.response.send_message(base_msg)
                return

            member = interaction.guild.get_member(target.id)
            if not member:
                await interaction.response.send_message(base_msg)
                return

            # Check for promotion
            promotion_due = await check_for_promotion(member)
            if promotion_due:
                base_msg += f"\n**{member.mention}** is due for promotion to **{promotion_due}**."

            await interaction.response.send_message(base_msg, allowed_mentions=discord.AllowedMentions.none())
            print(base_msg)

        return wrapper

    if _func is not None:
        return decorator(_func)
    return decorator


    # Handle both @promotion_check and @promotion_check(...)
    if _func is not None:
        return decorator(_func)
    return decorator

"""
BOT SETUP
"""

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
points_group = app_commands.Group(name="points", description= "EXP system")
log_group = app_commands.Group(name="log", description= "Logging actions")
stats_group = app_commands.Group(name="stats", description= "Bot statistics")
bot.tree.add_command(points_group)
bot.tree.add_command(log_group)
bot.tree.add_command(stats_group)

load_dotenv()

"""
EVENTS
"""

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} commands.")
    except Exception as e:
        print(f"Command sync failed: {e}")

"""
COMMANDS
"""

# /points check command
@points_group.command(
    name="check", description="Check the points of you or another member"
)
@app_commands.describe(user="User to check (optional)")
@promotion_check
async def points_check(interaction: discord.Interaction, user: discord.User = None):
    target = user or interaction.user
    points = get_points(target.id)
    msg = f"**{target.mention}** has **{points}** points."
    return msg

# /points add command
@points_group.command(name="add", description="Add points to a user")
@privileged_check("logistics")
@promotion_check
@app_commands.describe(user="User to add points to", amount="How many points to add")
async def points_add(
    interaction: discord.Interaction, user: discord.User, amount: float
):
    add_points(user.id, amount)
    amount = tidy_number(amount)
    msg = f"Added **{amount}** points to **{user.mention}**, bringing their total to **{get_points(user.id)}**."
    return msg

# /points subtract command
@points_group.command(name="subtract", description="Remove points from a user")
@privileged_check("logistics")
@app_commands.describe(
    user="User to remove points from", amount="How many points to remove"
)
async def points_subtract(
    interaction: discord.Interaction, user: discord.User, amount: float
):
    add_points(user.id, -abs(amount))
    amount = tidy_number(amount)
    msg = f"Removed **{abs(amount)}** points from **{user.mention}**, bringing their total to **{get_points(user.id)}**."
    await interaction.response.send_message(msg, allowed_mentions=discord.AllowedMentions.none())
    print(msg)

# /points set command
@points_group.command(name="set", description="Set the points of a user")
@privileged_check("logistics")
@promotion_check
@app_commands.describe(
    user="User to set the points of", amount="Amount of points to set"
)
async def points_set(
    interaction: discord.Interaction, user: discord.User, amount: float
):
    set_points(user.id, amount)
    amount = tidy_number(amount)
    msg = f"Set the points of **{user.mention}** to **{amount}**"
    return msg

# /stats ping
@stats_group.command(name="ping", description="Check the bot latency.")
async def ping(interaction: discord.Interaction):
    msg = f"Pong! {round(bot.latency * 1000)}ms"
    await interaction.response.send_message(msg, ephemeral=True)
    print(msg)

# /log rally command
@log_group.command(
    name="rally", description="Log the points for someone attending the weekly rally"
)
@privileged_check("logistics")
@app_commands.describe(
    user="User who attended the rally",
    amount_attendees="Amount of total attendees were at the rally",
    rally="Which rally was attended",
)
@app_commands.choices(
    rally=[
        app_commands.Choice(name="1 AM rally", value="1am"),
        app_commands.Choice(name="1 PM rally", value="1pm"),
    ]
)
@promotion_check
async def rally(
    interaction: discord.Interaction,
    user: discord.User,
    amount_attendees: int,
    rally: app_commands.Choice[str],
):
    if amount_attendees >= 5:
        added = get_value("rallyX5")
    else:
        added = get_value("rally")
    add_points(user.id, added)
    msg = f"Added **{added}** points to **{user.mention}** for representing ASOF at the **{rally.name}** with {str(amount_attendees - 1).replace("-1", "0")} other{"" if amount_attendees == 1 else "1"}."
    msg += f"\nThey now have **{get_points(user.id)}** points"
    return msg

# /log leaderboard command
@log_group.command(
    name="leaderboard",
    description="Log the points for someone completing leaderboard tasks",
)
@privileged_check("logistics")
@app_commands.describe(
    user="User who completed the leaderboard task",
    task="Which leaderboard task was completed",
    amount="How many times was the task completed",
)
@app_commands.choices(
    task=[
        app_commands.Choice(name="Visitor Transportation", value="visitortransport"),
        app_commands.Choice(name="Pizza Delivery", value="pizzadelivery"),
        app_commands.Choice(name="Bank Robbery", value="bank"),
        app_commands.Choice(name="Gold Bar Stolen", value="goldbar"),
        app_commands.Choice(name="Trainee Trained", value="trainee"),
        app_commands.Choice(name="Base Commander Elimination", value="basecommander"),
    ]
)
@promotion_check
async def log_leaderboard(
    interaction: discord.Interaction,
    user: discord.User,
    task: app_commands.Choice[str],
    amount: int = 1,
):
    added = get_value(task.value) * amount
    add_points(user.id, added)
    msg = f"Added **{added}** points to **{user.mention}** for "
    if task.value == "visitortransport":
        msg += f"transporting **{amount}** visitor{"" if amount == 1 else "1"}."
    elif task.value == "pizzadelivery":
        msg += f"delivering **{amount}** pizza{"" if amount == 1 else "s"}."
    elif task.value == "bank":
        msg += f"robbing **{amount}** bank{"" if amount == 1 else "s"}."
    elif task.value == "goldbar":
        msg += f"stealing **{amount}** gold bar{"" if amount == 1 else "s"}."
    elif task.value == "trainee":
        msg += f"training **{amount}** trainee{"" if amount == 1 else "s"}."
    elif task.value == "basecommander":
        msg += f"Eliminating **{amount}** Base Commander{"s" if amount > 1 else ""}."
    msg += f"\nThey now have **{get_points(user.id)}** points"
    return msg


# /log event
@log_group.command(
    name="event", description="Log the points for someone attending/hosting an event"
)
@privileged_check("logistics")
@app_commands.describe(
    user="User who attended/hosted the event",
    event_type="What type of event",
    attendance_type="How did they attend the event? (Attending, Hosting or Co-hosting)",
)
@app_commands.choices(
    event_type=[
        app_commands.Choice(name="Patrol", value="patrol"),
        app_commands.Choice(name="Gamenight", value="gamenight"),
        app_commands.Choice(name="Training", value="training"),
        app_commands.Choice(name="Raid", value="raid"),
        app_commands.Choice(name="Recruitment Session", value="recruitmentsession"),
    ]
)
@app_commands.choices(
    attendance_type=[
        app_commands.Choice(name="Attending", value="attending"),
        app_commands.Choice(name="Co Hosting", value="cohosting"),
        app_commands.Choice(name="Hosting", value="hosting"),
    ]
)
@promotion_check
async def event(
    interaction: discord.Interaction,
    user: discord.User,
    event_type: app_commands.Choice[str],
    attendance_type: app_commands.Choice[str],
):

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
    msg = f"Added **{added}** points to **{user.mention}** for {attendance_type.name.lower().replace(" ", "-")} a **{event_type.name}**."

    if booster_bonus > 0:  # Checks if member is a server booster
        msg += f"\n<:booster_icon:1425732545986822164> That includes an extra **{booster_bonus}** points for being a **Server Booster**! Thank you for supporting the division!"

    msg += f"\nThey now have **{get_points(user.id)}** points."

    return msg 

# Log ad command
@log_group.command(
    name="ad", description="Log the points for someone posting an advertisement"
)
@privileged_check("logistics")
@app_commands.describe(user="User who posted the advertisement", amount="Amount of advertisements posted in the past day")
@promotion_check
async def log_ad(
    interaction: discord.Interaction, user: discord.User, amount: int
    ):
    if amount == 3 or amount == 6:
        added = get_value("adX3")
    else:
        added = get_value("ad")
    add_points(user.id, added)
    msg = f"Added **{added}** points to **{user.mention}** for posting **{amount}** ads in one day"
    msg += f"\nThey now have **{get_points(user.id)}** points"
    return msg

# /log recruitment command
@log_group.command(
    name="recruitment",
    description="Log the points for someone recruiting a member in the Discord",
)
@privileged_check("logistics")
@app_commands.describe(
    user="User who recruited someone",
    amount="How many people were recruited (Optional)",
)
@promotion_check
async def recruitment(
    interaction: discord.Interaction, user: discord.User, amount: int = 1
):
    added = get_value("recruitment") * amount
    add_points(user.id, added)
    msg = f"Added **{added}** points to **{user.mention}** for **recruiting** **{amount}** members.\n"
    msg += f" They now have **{get_points(user.id)}** points."
    return msg

"""
LOG AUTO
"""

class View(discord.ui.View):
    confirm_log = 0
@discord.ui.button(label="Confirm log", style=discord.ButtonStyle.green, emoji="✅")
async def button_callback(self, button, interaction):
    confirm_log = 1
@discord.ui.button(label="Cancel log", style=discord.ButtonStyle.red, emoji="❌")
async def button_callback(self, button, interaction):
    confirm_log = 2

@log_group.command(name="auto", description="Automatically scan a log message and adds points accordingly. Powered by Google AI.")
@privileged_check("logistics")
@app_commands.describe(link="Link to the message to scan")
async def log_auto(interaction: discord.Interaction, link: str):
    await interaction.response.defer(thinking=True, ephemeral=True)

    try:
        # Parse the message link
        parts = link.split("/")
        guild_id, channel_id, message_id = int(parts[-3]), int(parts[-2]), int(parts[-1])
        channel = await bot.fetch_channel(channel_id)
        message = await channel.fetch_message(message_id)
    except Exception as e:
        await interaction.followup.send(f"Invalid message link: {e}")
        return
    
    # --- Build a readable version of the message ---
    msg_content = message.content

    # Replace mentions with readable names
    for user in message.mentions:
        msg_content = msg_content.replace(f"<@{user.id}>", f"<@{user.name}><@{user.id}>")
        msg_content = msg_content.replace(f"<@!{user.id}>", f"<@{user.name}><@{user.id}>")  # some clients use !id
    for role in message.role_mentions:
        msg_content = msg_content.replace(f"<@&{role.id}>", f"@{role.name}")
    for ch in message.channel_mentions:
        msg_content = msg_content.replace(f"<#{ch.id}>", f"#{ch.name}")

    channel_name = channel.name
    author = message.author.name

    # Determine log type based on channel
    if "recruit" in channel.name.lower():
        log_type = "recruitment"
    elif "event" in channel.name.lower():
        log_type = "event"
    elif "ad" in channel.name.lower():
        log_type = "ad"
    elif "leaderboard" in channel.category.name.lower():      # Leaderboard logs
        if "bank" in channel.name.lower():
            log_type = "bank"
        elif "visitor" in channel.name.lower():
            log_type = "visitortransport"
        elif "pizza" in channel.name.lower():
            log_type = "pizzadelivery"
        elif "base" in channel.name.lower():
            log_type = "basecommander"
        elif "training" in channel.name.lower():
            log_type = "training"
    
    # Build the prompt
    with open("prompts.toml", "rb") as f:
        prompts = tomllib.load(f)
    prompt = (prompts[log_type], prompts["ignore"], f"Sender: {author}", msg_content, prompts[log_type + "_footer"])
    prompt = "\n".join(prompt)
    client = genai.Client(
        api_key=os.getenv("GENAI_API_KEY")
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        config=types.GenerateContentConfig(
            system_instruction=prompts["header"]),
        contents=prompt
)

    print(response.text)
    aiOutput = response.text.lower().splitlines()
    print(aiOutput)
    await interaction.send_message(f"Confirm this data? \n {response.text}", view=View(), ephemeral=True)
    while button_callback.confirm_log == 0:
        await asyncio.sleep(0.1)
    if button_callback.confirm_log == 1:
        msg = ""
        for items in aiOutput:
            if "patrol" or "gamenight" or "training" or "raid" or "recruitmentsession" in aiOutput[0]:
                user_id = int(re.search(r"<@(\d+)>", aiOutput[0]).group(1))
                event_type = re.search(r"(patrol|gamenight|training|raid|recruitmentsession)", aiOutput[0]).group(1)
                attendance_type = re.search(r"(attending|hosting|cohosting)", aiOutput[0]).group(1)
                msg += f"\n{event(interaction=None, user=user_id, event_type=event_type, attendance_type=attendance_type)}"
            elif "lb" in aiOutput[0]:
                task = re.search(r"(bank|goldbar|basecommander|pizzadelivery|visitortransport|training)", aiOutput[0]).group(1)
                user_id = int(re.search(r"<@(\d+)>", aiOutput[0]).group(1))
                amount = int(re.search(r"(\d+)", aiOutput[0]).group(1))
                msg += f"\n{log_leaderboard(interaction=None, user=user_id, task=task, amount=amount)}"
            elif "ad" in aiOutput[0]:
                user_id = int(re.search(r"<@(\d+)>", aiOutput[0]).group(1))
                msg += f"\n{log_ad(interaction=None, user=user_id, amount=amount)}"
            elif "recruitment" in aiOutput[0]:
                user_id = int(re.search(r"<@(\d+)>", aiOutput[0]).group(1))
                amount = int(re.search(r"(\d+)", aiOutput[0]).group(1))
                msg += f"\n{recruitment(interaction=None, user=user_id, amount=amount)}"
            elif "rally" in aiOutput[0]:
                user_id = int(re.search(r"<@(\d+)>", aiOutput[0]).group(1))
                amount = int(re.search(r"(\d+)", aiOutput[0]).group(1))
                msg += f"\n{rally(interaction=None, user=user_id, amount=amount)}"
            del aiOutput[0]
        await interaction.followup.send(f"Logged successfully\n{msg}")

    elif button_callback.confirm_log == 2:
        await interaction.followup.send("Cancelled", ephemeral=True)
        return None
    
    
    

    
"""
RUN BOT
"""

bot.run(os.getenv("BETA_BOT_TOKEN"))
