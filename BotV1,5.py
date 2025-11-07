"""
ASOF BOT V1.5
"""

"""
IMPORTS
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import Button, View
import json
import os
import asyncio
import re
import sys
import functools
import tomllib
from datetime import datetime, timedelta
from google import genai
from google.genai import types  # type: ignore
from dotenv import load_dotenv  # type: ignore
from types import SimpleNamespace

"""
CONSTANTS
"""

POINTS_FILE = "points.json"
CONFIG_FILE = "config.json"
JSON_CLEANUP_INTERVAL = 12  # hours
REMOVE_AFTER_DAYS = 30  # days

"""
ROLES AND USER IDS
"""

test_id = 1353100755338530889
commander_id = 1382165268389957734
chiefofstaff_id = 1382165270780575844
chiefoflogistics_id = 1382165273049694299
logistics_id = 1383446002182262856
contractofficer_id = 1406564078666649660
nameplatedesigner_id = 1405169617751638076
booster_id = 1385279332049485935

ALWAYS_PRIVILEGED_ROLE_IDS = [test_id, commander_id, chiefofstaff_id]
ALWAYS_PRIVILEGED_USER_IDS = [805175554209873940]
PRIVILEGE_GROUP_ROLE_IDS = {
    "logistics": [logistics_id, chiefoflogistics_id],
    "config": [chiefoflogistics_id],
    "nameplatedesigner": [nameplatedesigner_id],
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


def edit_rank(name: str, role_id: int, points_required: int, requires_roles: list[int]):
    data = load_config()
    data["ranks"][name] = {
        "role_id": role_id,
        "points_required": points_required,
        "requires_roles": requires_roles,
    }
    save_config(data)


def remove_rank(name: str):
    data = load_config()
    if name in data["ranks"]:
        del data["ranks"][name]
        save_config(data)
        return True
    return False


def list_rank_names():
    return list(load_ranks().keys())


async def rank_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    ranks = list_rank_names()
    choices = [
        app_commands.Choice(name=r, value=r)
        for r in ranks
        if current.lower() in r.lower()
    ]
    # Add "Add New" option
    if "add new".startswith(current.lower()):
        choices.insert(0, app_commands.Choice(name="➕ Add New", value="__add_new__"))
    return choices[:25]


class RankEditModal(discord.ui.Modal, title="Add or Edit Rank"):
    def __init__(
        self,
        name: str = "",
        role_id: str = "",
        points_required: str = "",
        requires_roles: str = "",
    ):
        super().__init__()
        self.rank_name = discord.ui.TextInput(label="Rank Name", default=name)
        self.role_id = discord.ui.TextInput(label="Role ID", default=role_id)
        self.points_required = discord.ui.TextInput(
            label="Points Required", default=points_required
        )
        self.requires_roles = discord.ui.TextInput(
            label="Required Roles (comma-separated IDs)",
            default=requires_roles,
            required=False,
        )
        self.add_item(self.rank_name)
        self.add_item(self.role_id)
        self.add_item(self.points_required)
        self.add_item(self.requires_roles)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            name = self.rank_name.value.strip()
            role_id = int(self.role_id.value.strip())
            points_req = int(self.points_required.value.strip())
            requires = (
                [
                    int(x.strip())
                    for x in self.requires_roles.value.split(",")
                    if x.strip()
                ]
                if self.requires_roles.value.strip()
                else []
            )
            edit_rank(name, role_id, points_req, requires)
            msg = f"✅ Rank **{name}** saved successfully."
            await interaction.response.send_message(msg, ephemeral=True)
        except Exception as e:
            msg = f"Error: {e}"
            await interaction.response.send_message(msg, ephemeral=True)


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
        "pizzadelivery": 0,
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


def set_value(key: str, value: float):
    data = load_config()
    if "values" not in data:
        data["values"] = {}
    data["values"][key] = tidy_number(value)
    save_config(data)


def load_ranks():
    return load_config().get("ranks", {})


def add_rank(name: str, role_id: int, points_required: int, requires_roles: list[int]):
    data = load_config()
    data["ranks"][name] = {
        "role_id": role_id,
        "points_required": points_required,
        "requires_roles": requires_roles,
    }
    save_config(data)


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
        ranks.items(), key=lambda x: x[1]["points_required"], reverse=True
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
            points >= required_points
            and all(rid in user_role_ids for rid in required_roles)
            and role_id not in user_role_ids
        ):
            return name

    return None


def promotion_check(_func=None, *, target_param: str = "user"):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(interaction: discord.Interaction, *args, **kwargs):
            # detect if "suppress_send" is passed in kwargs
            suppress_send = kwargs.pop("suppress_send", False)

            base_msg = await func(interaction, *args, **kwargs)
            if not isinstance(base_msg, str):
                base_msg = ""

            target = kwargs.get(target_param, None)
            if not target and len(args) > 0:
                target = args[0]

            if not isinstance(target, (discord.User, discord.Member)):
                if not suppress_send:  # only send if not suppressed
                    await interaction.response.send_message(base_msg)
                return base_msg

            member = interaction.guild.get_member(target.id)
            if not member:
                if not suppress_send:
                    await interaction.response.send_message(base_msg)
                return base_msg

            promotion_due = await check_for_promotion(member)
            if promotion_due:
                base_msg += f"\n**{member.mention}** is due for promotion to **{promotion_due}**."

            if not suppress_send:
                await interaction.response.send_message(
                    base_msg, allowed_mentions=discord.AllowedMentions.none()
                )

            print(base_msg)
            return base_msg

        return wrapper

    if _func is not None:
        return decorator(_func)
    return decorator


@promotion_check
async def promotion_check_2(interaction, user):
    return None


"""
SETUP
"""

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="/", intents=intents)
points_group = app_commands.Group(name="points", description="EXP system")
log_group = app_commands.Group(name="log", description="Logging actions")
stats_group = app_commands.Group(name="stats", description="Bot statistics")
config_group = app_commands.Group(name="config", description="Bot configuration")
bot.tree.add_command(points_group)
bot.tree.add_command(log_group)
bot.tree.add_command(stats_group)
bot.tree.add_command(config_group)
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


@bot.event
async def on_member_join(member):
    data = load_points()
    if str(member.id) not in data:
        data[str(member.id)] = {"points": 0, "left_at": None}
        save_points(data)
        print(f"Added {member.name} to points.json")


@bot.event
async def on_member_remove(member):
    data = load_points()
    if str(member.id) in data:
        data[str(member.id)]["left_at"] = datetime.now().isoformat()
        save_points(data)
        print(f"Marked {member.name} as left at {datetime.now().isoformat()}")


@tasks.loop(hours=JSON_CLEANUP_INTERVAL)
async def cleanup_inactive_users():
    data = load_points()
    now = datetime.utcnow()
    removed = [
        uid
        for uid, info in data.items()
        if info.get("left_at")
        and now - datetime.fromisoformat(info["left_at"])
        > timedelta(days=REMOVE_AFTER_DAYS)
    ]
    for uid in removed:
        del data[uid]
    if removed:
        save_points(data)
        print(
            f"Removed {len(removed)} users inactive for over {REMOVE_AFTER_DAYS} days."
        )


"""
COMMANDS
"""


# /stats ping
@stats_group.command(name="ping", description="Check the bot latency.")
async def ping(interaction: discord.Interaction):
    msg = f"Pong! {round(bot.latency * 1000)}ms"
    await interaction.response.send_message(msg, ephemeral=True)
    print(msg)


# /config values
@config_group.command(
    name="values", description="configures the points values of different actions"
)
@privileged_check("config")
@app_commands.describe(
    type="What action to edit the values for", value="What to set the value to"
)
@app_commands.choices(
    type=[
        app_commands.Choice(name="ad", value="ad"),
        app_commands.Choice(name="ad x3", value="adX3"),
        app_commands.Choice(name="recruitment", value="recruitment"),
        app_commands.Choice(name="recruitment session", value="recruitmentsession"),
        app_commands.Choice(name="rally", value="rally"),
        app_commands.Choice(name="rally with 5 or more people", value="rallyX5"),
        app_commands.Choice(name="patrol", value="patrol"),
        app_commands.Choice(name="gamenight", value="gamenight"),
        app_commands.Choice(name="training", value="training"),
        app_commands.Choice(name="raid", value="raid"),
        app_commands.Choice(name="event hosting", value="hosting"),
        app_commands.Choice(name="event co-hosting", value="cohosting"),
        app_commands.Choice(name="server booster event bonus", value="booster"),
        app_commands.Choice(
            name="joint event with other divisions bonus", value="joint"
        ),
        app_commands.Choice(name="logistics event logging", value="eventlogging"),
        app_commands.Choice(
            name="contract officer completed payment", value="contractpayment"
        ),
        app_commands.Choice(name="nameplate order completed", value="nameplate"),
        app_commands.Choice(
            name="leaderboard base commander kill", value="basecommander"
        ),
        app_commands.Choice(name="leaderboard bank robbery completed", value="bank"),
        app_commands.Choice(name="leaderboard gold bar stolen", value="goldbar"),
        app_commands.Choice(name="leaderboard trainee trained", value="trainee"),
        app_commands.Choice(
            name="leaderboard visitor transported", value="visitortransport"
        ),
        app_commands.Choice(name="leaderboard pizza delivered", value="pizzadelivery"),
    ]
)
async def config_values(
    interaction: discord.Interaction, type: app_commands.Choice[str], value: float
):
    set_value(type.value, value)
    msg = f"Set value of **{type.value}** to **{get_value(type.value)}**"
    await interaction.response.send_message(msg)
    print(msg)


# /config ranks
@config_group.command(name="ranks", description="Add or edit a rank")
@privileged_check("config")
@app_commands.autocomplete(rank=rank_autocomplete)
@app_commands.describe(rank="Select a rank to edit or 'Add New'")
async def config_ranks_edit(interaction: discord.Interaction, rank: str):
    if rank == "__add_new__":
        # Empty modal for new rank
        await interaction.response.send_modal(RankEditModal())
    else:
        ranks = load_ranks()
        r = ranks.get(rank, {})
        modal = RankEditModal(
            name=rank,
            role_id=str(r.get("role_id", "")),
            points_required=str(r.get("points_required", "")),
            requires_roles=",".join(str(x) for x in r.get("requires_roles", [])),
        )
        await interaction.response.send_modal(modal)


@config_group.command(name="ranks_remove", description="Remove a rank")
@privileged_check("config")
@app_commands.autocomplete(rank=rank_autocomplete)
@app_commands.describe(rank="Select rank to remove")
async def config_ranks_remove(interaction: discord.Interaction, rank: str):
    if rank == "__add_new__":
        msg = "No"
        await interaction.response.send_message(msg, ephemeral=True)
        print(msg)
        return

    if remove_rank(rank):
        msg = f"Removed rank **{rank}**"
        await interaction.response.send_message(msg)
        print(msg)
    else:
        msg = f"Rank **{rank}** not found."
        await interaction.response.send_message(msg, ephemeral=True)
        print(msg)


@stats_group.command(name="ranks", description="List all ranks and their requirements")
async def config_ranks_list(interaction: discord.Interaction):
    ranks = load_ranks()
    if not ranks:
        msg = "No ranks configured yet."
        await interaction.response.send_message(msg, ephemeral=True)
        print(msg)
        return

    msg = "**Configured Ranks:**\n\n"
    for name, info in ranks.items():
        required_roles = ", ".join(f"<@&{r}>" for r in info["requires_roles"]) or "None"
        msg += (
            f"**{name} (<@&{info['role_id']}>)**\n"
            f"Points: {info['points_required']}\n"
            f"Required Roles: {required_roles}\n\n"
        )

    await interaction.response.send_message(msg, ephemeral=True)
    print(msg)


# /points check command
@points_group.command(
    name="check", description="Check the points of you or another member"
)
@app_commands.describe(user="User to check (optional)")
@promotion_check
async def points_check(interaction: discord.Interaction, user: discord.User = None):
    target = user or interaction.user
    points = get_points(target.id)
    msg = ""
    if points >= 5000:
        msg = "🤑 "
    elif points == 100:
        msg = "💯"
    msg += f"**{target.mention}** has **{points}** points."
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
    await interaction.response.send_message(
        msg, allowed_mentions=discord.AllowedMentions.none()
    )
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


# /log rally command
async def rally_logic(interaction, user, amount_attendees):
    if amount_attendees >= 5:
        added = get_value("rallyX5")
    else:
        added = get_value("rally")
    add_points(user.id, added)
    msg = f"Added **{added}** points to **{user.mention}** for representing ASOF at a SEA Rally"
    msg += f"\nThey now have **{get_points(user.id)}** points"
    return msg


@log_group.command(
    name="rally", description="Log the points for someone attending the weekly rally"
)
@privileged_check("logistics")
@app_commands.describe(
    user="User who attended the rally",
    amount_attendees="Amount of total attendees were at the rally",
)
@promotion_check
async def rally(
    interaction: discord.Interaction,
    user: discord.User,
    amount_attendees: int,
):
    msg = await rally_logic(interaction, user, amount_attendees)
    return msg


# /log leaderboard command
async def log_leaderboard_logic(interaction, user, task, amount):
    if isinstance(task, str):
        task = SimpleNamespace(value=task, name=task.capitalize())
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
    msg = await log_leaderboard_logic(interaction, user, task, amount)
    return msg


# /log event command
async def event_logic(interaction, user, event_type, attendance_type):
    if isinstance(event_type, str):
        event_type = SimpleNamespace(value=event_type.replace(" ", ""), name=event_type.capitalize())
    if isinstance(attendance_type, str):
        attendance_type = SimpleNamespace(
            value=attendance_type, name=attendance_type.capitalize()
        )

    added = get_value(event_type.value)
    if not attendance_type.value == "attending":
        added += get_value(attendance_type.value)

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
    msg = await event_logic(interaction, user, event_type, attendance_type)
    return msg


# Log ad command
async def ad_logic(interaction, user, amount):
    if amount == 3 or amount == 6:
        added = get_value("adX3")
    else:
        added = get_value("ad")
    add_points(user.id, added)
    msg = f"Added **{added}** points to **{user.mention}** for posting **{amount}** ads in one day"
    msg += f"\nThey now have **{get_points(user.id)}** points"
    return msg


@log_group.command(
    name="ad", description="Log the points for someone posting an advertisement"
)
@privileged_check("logistics")
@app_commands.describe(
    user="User who posted the advertisement",
    amount="Amount of advertisements posted in the past day",
)
@promotion_check
async def log_ad(interaction: discord.Interaction, user: discord.User, amount: int):
    msg = await ad_logic(interaction, user, amount)
    return msg


# /log recruitment command
async def recruitment_logic(interaction, user, amount):
    added = get_value("recruitment") * amount
    add_points(user.id, added)
    msg = f"Added **{added}** points to **{user.mention}** for **recruiting** **{amount}** members.\n"
    msg += f" They now have **{get_points(user.id)}** points."
    return msg


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
    msg = await recruitment_logic(interaction, user, amount)
    return msg


"""
LOG AUTO
"""


class ConfirmLogView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.value = None  # stores the button result

    @discord.ui.button(label="Confirm log", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        self.value = True
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()


@log_group.command(
    name="auto",
    description=f"Automatically scan a log message and adds points accordingly. Powered by Google AI.",
)
@privileged_check("logistics")
@app_commands.describe(link="Link to the message to scan")
async def log_auto(interaction: discord.Interaction, link: str):
    await interaction.response.send_message("<:gemini:1436266313109733397> Analysing log <a:loading3:1436270707267993610>")

    try:
        # Parse the message link
        parts = link.split("/")
        guild_id, channel_id, message_id = (
            int(parts[-3]),
            int(parts[-2]),
            int(parts[-1]),
        )
        channel = await bot.fetch_channel(channel_id)
        message = await channel.fetch_message(message_id)
    except Exception as e:
        await interaction.edit_original_response(content=f"Invalid message link: {e}")
        await asyncio.sleep(5)
        await interaction.delete_original_response()
        return

    msg_content = message.content
    for role in message.role_mentions:
        msg_content = msg_content.replace(f"<@&{role.id}>", f"@{role.name}")
    for ch in message.channel_mentions:
        msg_content = msg_content.replace(f"<#{ch.id}>", f"#{ch.name}")

    channel_name = channel.name
    author = message.author.id

    # Determine log type based on channel
    if "recruit" in channel.name.lower():
        log_type = "recruitment"
    elif "event" in channel.name.lower():
        log_type = "event"
    elif "ad" in channel.name.lower():
        log_type = "ad"
    elif "leaderboard" in channel.category.name.lower():  # Leaderboard logs
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
    prompt = (
        prompts[log_type],
        prompts["ignore"],
        f"Message author: <@{author}>",
        msg_content,
        prompts[log_type + "_footer"],
    )
    prompt = "\n".join(prompt)
    client = genai.Client(api_key=os.getenv("GENAI_API_KEY"))

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        config=types.GenerateContentConfig(system_instruction=prompts["header"]),
        contents=prompt,
    )

    print(response.text)
    aiOutput = response.text.lower().splitlines()
    print(aiOutput)
    view = ConfirmLogView()
    await interaction.followup.send(
        f"Confirm this data?\n>>> {response.text}", view=view, ephemeral=True
    )
    await view.wait()

    if view.value is None:
        await interaction.edit_original_response(content="Timed out")
        await asyncio.sleep(5)
        await interaction.delete_original_response()
    elif view.value:
        msg = ""
        i = 0
        for items in aiOutput:
            lower = items.lower()
            if any(
                word in aiOutput[i].lower().replace(" ", "")
                for word in [
                    "patrol",
                    "gamenight",
                    "training",
                    "raid",
                    "recruitmentsession",
                ]
            ):
                user = interaction.guild.get_member(
                    int(re.search(r"<@(\d+)>", aiOutput[i].lower()).group(1))
                )
                event_type = re.search(
                    r"(patrol|gamenight|training|raid|recruitment session)",
                    aiOutput[i].lower()
                ).group(1)
                attendance_type = re.search(
                    r"(attend|cohost|host)", aiOutput[i].lower()
                ).group(1)

                attendance_type += "ing"
                print(attendance_type)
                msg += f"\n{await event_logic(interaction, user=user, event_type=event_type, attendance_type=attendance_type)}"
                msg += await promotion_check_2(
                    interaction, user=user, suppress_send=True
                )
            elif "lb" in aiOutput[i]:
                user = interaction.guild.get_member(
                    int(re.search(r"<@(\d+)>", aiOutput[i].lower()).group(1))
                )
                all_numbers = re.findall(r"\b\d+\b", lower)
                amount = (
                    int(all_numbers[-1]) if all_numbers else 1
                )  # make sure it gets the amount, not the user ID
                msg += f"\n{await log_leaderboard_logic(interaction, user=user, task=log_type, amount=amount)}"
            elif log_type == "ad":
                user = interaction.guild.get_member(
                    int(re.search(r"<@(\d+)>", aiOutput[i].lower()).group(1))
                )
                all_numbers = re.findall(r"\b\d+\b", lower)
                amount = (
                    int(all_numbers[-1]) if all_numbers else 1
                )  # make sure it gets the amount, not the user ID
                msg += f"\n{await ad_logic(interaction, user=user, amount=amount)}"
            elif log_type == "recruitment":
                user = interaction.guild.get_member(
                    int(re.search(r"<@(\d+)>", aiOutput[i].lower()).group(1))
                )
                all_numbers = re.findall(r"\b\d+\b", lower)
                amount = (
                    int(all_numbers[-1]) if all_numbers else 1
                )  # make sure it gets the amount, not the user ID
                msg += f"\n{await recruitment_logic(interaction, user=user, amount=amount)}"
            elif "rally" in aiOutput[i]:
                user = interaction.guild.get_member(
                    int(re.search(r"<@(\d+)>", aiOutput[i].lower()).group(1))
                )
                amount_attendees = len(aiOutput)
                msg += f"\n{await rally_logic(interaction, user=user, amount_attendees=amount_attendees)}"
            else:
                continue
            print(aiOutput[i])
            i += 1
        await interaction.edit_original_response(content=f"Logged successfully\n{msg}")
    else:
        await interaction.edit_original_response(content="Cancelled.")
        await asyncio.sleep(5)
        await interaction.delete_original_response()
        await asyncio.sleep(0.1)


"""
POINTS LEADERBOARD
"""


# Autocomplete function
async def leaderboard_page_autocomplete(interaction: discord.Interaction, current: str):
    points_data = load_points()
    per_page = 10
    total_pages = (len(points_data) + per_page - 1) // per_page or 1

    suggestions = [
        app_commands.Choice(name=str(i), value=str(i))
        for i in range(1, total_pages + 1)
    ]
    suggestions.append(app_commands.Choice(name="all", value="all"))

    return [s for s in suggestions if current.lower() in s.name.lower()]


# /leaderboard command
@bot.tree.command(
    name="leaderboard", description="Shows how many points people have on a leaderboard"
)
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

    # Handle 'all' mode
    if page.lower() == "all":
        display_list = leaderboard_list
        ephemeral = True
        page_num = 1
    else:
        try:
            page_num = int(page)
            if page_num < 1 or page_num > total_pages:
                await interaction.response.send_message(
                    f"Invalid page number. There {'are only **'+str(total_pages)+'** pages' if total_pages > 1 else 'is only **1** page'}.",
                    ephemeral=True,
                )
                return
        except ValueError:
            await interaction.response.send_message(
                f"Page must be {'a number (1 to '+str(total_pages)+')' if total_pages > 1 else '1'} or `all`.",
                ephemeral=True,
            )
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
        name = member.mention if member else f"Unknown User ({user_id})"
        points_display = int(points) if float(points).is_integer() else points
        lines.append(f"**#{rank}** — {name}: {points_display} points")

    if page.lower() == "all":
        title = f"🏆 Full Leaderboard — {len(leaderboard_list)} players"
    else:
        title = f"🏆 Leaderboard — Page {page_num}/{total_pages}"

    # Split message into chunks to respect Discord’s 2000-character limit
    max_length = 1900
    message = f"{title}\n"
    chunks = []

    for line in lines:
        if len(message) + len(line) + 1 > max_length:
            chunks.append(message)
            message = ""
        message += line + "\n"
    if message:
        chunks.append(message)

    # Send first chunk as initial response
    await interaction.response.send_message(
        chunks[0],
        allowed_mentions=discord.AllowedMentions.none(),
        ephemeral=ephemeral,
    )

    # Send remaining chunks as followups
    for chunk in chunks[1:]:
        await interaction.followup.send(
            chunk,
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=ephemeral,
        )


"""
RUN BOT
"""

bot.run(os.getenv("BOT_TOKEN"))
