import discord
from discord.ext import commands, tasks
import requests
import asyncio
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import certifi
import time

# Load .env variables
load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
TOKEN = os.getenv("TOKEN")
PUBG_API_KEY = os.getenv("PUBG_API_KEY").strip()

# CONFIG
CHANNEL_ID = int(os.getenv("CHANNEL_ID", 1329872665787240541))  # fallback la default
PLATFORM = "steam"
sleep_time = 30

# Discord intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# MongoDB setup
try:
    client = MongoClient(MONGO_URI, tlsCAFile=certifi.where())
    db = client["pubg_bot"]
    players_col = db["players"]
    matches_col = db["processedMatches"]
    global_col = db["globalStats"]
    print("✅ Connected to MongoDB!")
except Exception as e:
    print(f"❌ Error connecting with MongoDB: {e}")
    raise

async def safe_request(url, headers, max_retries=3, base_delay=5):
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers)
        if response.status_code != 429:
            return response
        delay = base_delay * (2 ** attempt)
        print(f"⚠️ Rate limit 429 – test {attempt + 1}/{max_retries}, we are waiting {delay}s...")
        await asyncio.sleep(delay)
    return response

async def get_player_ids():
    headers = {"Authorization": f"Bearer {PUBG_API_KEY}", "Accept": "application/vnd.api+json"}
    for player in players_col.find():
        if player.get("accountId"):
            continue
        url = f"https://api.pubg.com/shards/{PLATFORM}/players?filter[playerNames]={player['username']}"
        response = await safe_request(url, headers)
        if response.status_code == 200 and response.json()["data"]:
            account_id = response.json()["data"][0]["id"]
            players_col.update_one({"username": player["username"]}, {"$set": {"accountId": account_id}})

async def get_last_match(player_id):
    url = f"https://api.pubg.com/shards/{PLATFORM}/players/{player_id}"
    headers = {"Authorization": f"Bearer {PUBG_API_KEY}", "Accept": "application/vnd.api+json"}
    response = await safe_request(url, headers)
    if response.status_code == 200:
        matches = response.json()["data"]["relationships"]["matches"]["data"]
        if matches:
            return matches[0]["id"]
    return None

def filter_by_id(players, player_id):
    for player in players:
        if player.get("type") == "participant" and player["attributes"]["stats"]["playerId"] == player_id:
            return player
    return None

async def save_longest_kill(username, distance):
    channel = bot.get_channel(CHANNEL_ID)
    player = players_col.find_one({"username": username})
    if not player:
        return

    if distance > player.get("longestKill", 0):
        players_col.update_one({"username": username}, {"$set": {"longestKill": distance}})

    global_record = global_col.find_one({"_id": "globalLongestKill"}) or {"distance": 0}
    if distance > global_record["distance"]:
        global_col.replace_one(
            {"_id": "globalLongestKill"},
            {"_id": "globalLongestKill", "username": username, "distance": distance},
            upsert=True
        )
        await channel.send(f"🎯 **NOU RECORD!** 🎯\n{username} a reușit un kill de la **{distance} metri**! 🚀🥇")

async def get_player_info(player_id):
    last_match_id = await get_last_match(player_id)
    if not last_match_id:
        return None

    match_key = f"{player_id}:{last_match_id}"
    if matches_col.find_one({"matchId": match_key}):
        return None

    url = f"https://api.pubg.com/shards/{PLATFORM}/matches/{last_match_id}"
    headers = {"Authorization": f"Bearer {PUBG_API_KEY}", "Accept": "application/vnd.api+json"}
    response = await safe_request(url, headers)
    if response.status_code == 200:
        match_data = response.json()
        game_mode = match_data["data"]["attributes"]["gameMode"]
        match_type = match_data["data"]["attributes"].get("matchType", "")

        print(f"Mod detectat pentru {player_id}: gameMode = {game_mode}, matchType = {match_type}")

        if game_mode in ["arcade", "skbd", "lab", "war", "bluebomb", "esportsmode", "gunplay_ibr", "ibr", "tdm", "tutorialatoz", "slbmiramar-fpp"] or match_type in ["custom", "event", "tutorialatoz", "airoyale"]:
            return None

        filtered_player = filter_by_id(match_data["included"], player_id)
        if filtered_player and "winPlace" in filtered_player["attributes"]["stats"]:
            matches_col.insert_one({"matchId": match_key, "processed": True})
            return filtered_player["attributes"]["stats"]
    return None

@tasks.loop(minutes=5)
async def check_for_wins():
    await get_player_ids()
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    for player in players_col.find():
        username = player["username"]
        player_id = player.get("accountId")
        if not player_id:
            continue

        stats = await get_player_info(player_id)
        if not stats:
            print(f"⏭️ Match for {username} skipped (already processed or invalid)")
            continue

        win_place = stats["winPlace"]
        damage = stats["damageDealt"]
        kills = stats["kills"]
        longest_kill = stats["longestKill"]
        assists = stats.get("assists", 0)
        max_damage = player.get("maxDamage", 0)
        if damage > max_damage:
            players_col.update_one({"username": username}, {"$set": {"maxDamage": damage}})

        update_data = {
            "$inc": {
                "damage": int(damage),
                "kills": int(kills),
                "assists": int(assists),
                "matchCount": 1,
                "score": 1 if win_place == 1 else 0
            }
        }
        if damage > player.get("maxSingleMatchDamage", 0):
            players_col.update_one(
                {"username": username},
                {"$set": {"maxSingleMatchDamage": damage}}
            )
        players_col.update_one({"username": username}, update_data)
        bot.loop.create_task(save_longest_kill(username, longest_kill))

        if win_place == 1:
            embed = discord.Embed(
                title="🏆 Winner Winner Chicken Dinner!",
                description=f"**{username}** has won a PUBG match! 🎉",
                color=discord.Color.blue()
            )

            embed.add_field(name="🎯 Placement", value=f"#1", inline=True)
            embed.add_field(name="🔫 Kills", value=str(kills), inline=True)
            embed.add_field(name="💥 Damage Dealt", value=f"{damage:.1f}", inline=True)
            embed.add_field(name="📏 Longest Kill", value=f"{longest_kill:.1f} meters", inline=True)

            embed.set_footer(text="PUBG Discord Bot by ClashRanks • Made for PUBG players")

            await channel.send("@everyone", embed=embed) 

        print(f"📊 {username} finished on the spot {win_place}, {kills} kills, {damage} damage")
        await asyncio.sleep(sleep_time)

@bot.command()
async def wins(ctx):
    guild_id = ctx.guild.id
    top = list(players_col.find({"guild_id": guild_id}).sort("score", -1).limit(10))

    if not top:
        await ctx.send("There is no data.")
        return

    embed = discord.Embed(
        title="🏆 Leaderboard - Wins",
        description="Top players ranked by number of wins",
        color=discord.Color.blue()
    )

    for i, p in enumerate(top, start=1):
        embed.add_field(
            name=f"{i}. {p['username']}",
            value=f"{p['score']} win{'s' if p['score'] != 1 else ''}",
            inline=False
        )

    embed.set_footer(text="PUBG Discord Bot by ClashRanks • Made for PUBG players")
    await ctx.send(embed=embed)

@bot.command()
async def damage(ctx):
    guild_id = ctx.guild.id
    players = list(players_col.find({"guild_id": guild_id}))

    if not players:
        await ctx.send("No data available.")
        return

    sorted_damages = sorted(players, key=lambda p: (p["damage"] / max(1, p["matchCount"])), reverse=True)

    embed = discord.Embed(
        title="🔥 Leaderboard - Average Damage per Match",
        description="Top players based on damage dealt per match",
        color=discord.Color.blue()
    )

    for i, p in enumerate(sorted_damages[:10], start=1):
        dmg = p["damage"] / max(1, p["matchCount"])
        embed.add_field(
            name=f"{i}. {p['username']}",
            value=f"{dmg:.2f} damage/match",
            inline=False
        )

    embed.set_footer(text="PUBG Discord Bot by ClashRanks • Made for PUBG players")
    await ctx.send(embed=embed)

@bot.command()
async def kills(ctx):
    guild_id = ctx.guild.id
    top = list(players_col.find({"guild_id": guild_id}).sort("kills", -1).limit(10))

    if not top:
        await ctx.send("No data available.")
        return

    embed = discord.Embed(
        title="🔫 Leaderboard - Kills",
        description="Top players ranked by total kills",
        color=discord.Color.blue()
    )

    for i, p in enumerate(top, start=1):
        embed.add_field(
            name=f"{i}. {p['username']}",
            value=f"{p['kills']} kills",
            inline=False
        )

    embed.set_footer(text="PUBG Discord Bot by ClashRanks • Made for PUBG players")
    await ctx.send(embed=embed)


@bot.command()
async def sniper(ctx):
    guild_id = ctx.guild.id
    top = list(players_col.find({"guild_id": guild_id}).sort("longestKill", -1).limit(10))

    if not top:
        await ctx.send("No data available.")
        return

    embed = discord.Embed(
        title="🎯 Leaderboard - Longest Kill Shots",
        description="Top sniper kills (longest distance)",
        color=discord.Color.blue()
    )

    for i, p in enumerate(top, start=1):
        embed.add_field(
            name=f"{i}. {p['username']}",
            value=f"{p['longestKill']} meters",
            inline=False
        )

    embed.set_footer(text="PUBG Discord Bot by ClashRanks • Made for PUBG players")
    await ctx.send(embed=embed)

@bot.command()
async def maxdamage(ctx):
    guild_id = ctx.guild.id
    top = list(players_col.find({"guild_id": guild_id}).sort("maxSingleMatchDamage", -1).limit(10))

    if not top:
        await ctx.send("No data available.")
        return

    embed = discord.Embed(
        title="💥 Most Damage in a Single Match",
        description="Top players by highest single-match damage",
        color=discord.Color.blue()
    )

    for i, p in enumerate(top, start=1):
        embed.add_field(
            name=f"{i}. {p['username']}",
            value=f"{p.get('maxSingleMatchDamage', 0):.1f} damage",
            inline=False
        )

    embed.set_footer(text="PUBG Discord Bot by ClashRanks • Made for PUBG players")
    await ctx.send(embed=embed)

@bot.command()
async def kda(ctx):
    guild_id = ctx.guild.id
    players = list(players_col.find({"guild_id": guild_id}))

    if not players:
        await ctx.send("No data available.")
        return

    sorted_kda = sorted(
        players,
        key=lambda p: ((p.get("kills", 0) + p.get("assists", 0)) / max(1, p.get("matchCount", 1))),
        reverse=True
    )

    embed = discord.Embed(
        title="📈 Leaderboard - KDA",
        description="Top players based on KDA = (Kills + Assists) / Matches",
        color=discord.Color.blue()
    )

    for i, p in enumerate(sorted_kda[:10], start=1):
        k = p.get("kills", 0)
        a = p.get("assists", 0)
        m = max(1, p.get("matchCount", 1))
        kda_val = (k + a) / m
        embed.add_field(
            name=f"{i}. {p['username']}",
            value=f"{kda_val:.2f}",
            inline=False
        )

    embed.set_footer(text="PUBG Discord Bot by ClashRanks • Made for PUBG players")
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def add_user(ctx, pubg_name):
    clean_name = pubg_name.strip()
    existing = players_col.find_one({
        "username": {"$regex": f"^{pubg_name}$", "$options": "i"},
        "guild_id": ctx.guild.id
    })
    if existing:
        await ctx.send(f"❗ Player `{pubg_name}` is already registered.")
        return

    headers = {
        "Authorization": f"Bearer {PUBG_API_KEY}",
        "Accept": "application/vnd.api+json"
    }

    url = f"https://api.pubg.com/shards/steam/players?filter[playerNames]={pubg_name.strip()}"
    response = await safe_request(url, headers)

    if response.status_code == 429:
        await ctx.send("⚠️ You have been temporarily blocked by the PUBG API (429 Too Many Requests). Please try again in a few seconds.")
        return

    if response.status_code != 200:
        await ctx.send(f"❌ Error API PUBG ({response.status_code}): {response.text}")
        return

    data = response.json().get("data")
    if not data:
        await ctx.send(f"❌ Player not found `{pubg_name}`.")
        return

    account_id = data[0]["id"]
    players_col.insert_one({
        "username": clean_name,
        "accountId": account_id,
        "damage": 0,
        "kills": 0,
        "assists": 0,
        "maxDamage": 0,
        "score": 0,
        "matchCount": 0,
        "longestKill": 0,
        "guild_id": ctx.guild.id
    })

    await ctx.send(f"✅ Player **{pubg_name}** has been added to the leaderboard!")

@bot.command()
@commands.has_permissions(administrator=True)
async def remove_user(ctx, pubg_name):
    regex_filter = {"$regex": f"^{pubg_name}$", "$options": "i"}
    result = players_col.delete_many({"username": regex_filter, "guild_id": ctx.guild.id})
    if result.deleted_count == 0:
        await ctx.send(f"❗ Player `{pubg_name}` not found.")
    else:
        await ctx.send(f"🗑️ I deleted {result.deleted_count} entries for")

@bot.command()
async def help(ctx):
    embed = discord.Embed(
        title="📘 PUBG Bot - Command Guide",
        description="Here are all the available commands you can use:",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="🎯 Player Stats",
        value=(
            "`!wins`               - Displays the leaderboard for wins\n"
            "`!kills`              - Displays the leaderboard for kills\n"
            "`!damage`             - Displays the leaderboard for average damage per match\n"
            "`!sniper`             - Displays the leaderboard for longest kill shots\n"
            "`!maxdamage`          - Displays the leaderboard for highest damage in a single match\n"
            "`!kda`                - Displays the leaderboard based on KDA\n"
            "`!profile <PUBGName>` - Displays your stats or another player's profile"

        ),
        inline=False
    )

    embed.add_field(
        name="⚙️ Admin Commands",
        value=(
            "`!add_user <PUBGName>`     - Add a player to the leaderboard\n"
            "`!remove_user <PUBGName>`  - Remove a player from the leaderboard\n"
            "`!reset <fields>`          - Reset selected stats for all players (e.g. !reset all or !reset kills,damage)"

        ),
        inline=False
    )

    embed.set_footer(text="PUBG Discord Bot by ClashRanks • Made for PUBG players")

    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def reset(ctx, fields: str):
    guild_id = ctx.guild.id

    valid_fields = {
        "damage": "damage",
        "kills": "kills",
        "score": "score",
        "matchcount": "matchCount"
    }

    fields_input = fields.strip().lower()

    if fields_input == "all":
        to_reset = list(valid_fields.values())
    else:
        requested = set(f.strip().lower() for f in fields.split(","))
        invalid = requested - set(valid_fields.keys())

        if invalid:
            await ctx.send(
                f"❌ Invalid fields: {', '.join(invalid)}\n✅ Valid options: {', '.join(valid_fields.keys())}"
            )
            return

        to_reset = [valid_fields[f] for f in requested]

    update = {"$set": {key: 0 for key in to_reset}}
    result = players_col.update_many({"guild_id": guild_id}, update)

    await ctx.send(f"✅ Reset `{', '.join(to_reset)}` for {result.modified_count} players.")

@bot.command()
async def profile(ctx, player_name: str = None):
    guild_id = ctx.guild.id
    query_name = player_name or ctx.author.name

    player = players_col.find_one({
        "username": {"$regex": f"^{query_name}$", "$options": "i"},
        "guild_id": guild_id
    })

    if not player:
        await ctx.send(f"❌ Player `{query_name}` not found in leaderboard.")
        return

    match_count = max(1, player.get("matchCount", 0)) 
    avg_damage = player.get("damage", 0) / match_count

    embed = discord.Embed(
        title=f"📊 PUBG Profile: {player['username']}",
        color=discord.Color.blue()
    )

    embed.add_field(name="🏆 Wins", value=player.get("score", 0), inline=True)
    embed.add_field(name="🔫 Kills", value=player.get("kills", 0), inline=True)
    embed.add_field(name="💥 Avg. Damage", value=f"{avg_damage:.2f}", inline=True)
    embed.add_field(name="💣 Max Damage", value=f"{player.get('maxDamage', 0):.1f}", inline=True)
    embed.add_field(name="🧠 Assists", value=player.get("assists", 0), inline=True)
    embed.add_field(name="📏 Longest Kill", value=f"{player.get('longestKill', 0)} m", inline=True)
    embed.add_field(name="🎮 Matches Played", value=player.get("matchCount", 0), inline=True)

    embed.set_footer(text="PUBG Discord Bot by ClashRanks")
    embed.timestamp = discord.utils.utcnow()

    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def announce_season2(ctx):
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        await ctx.send("❌ Announcement channel not found.")
        return

    embed = discord.Embed(
        title="🎉 Season 2 Has Started!",
        description=(
            "A new competitive season has officially begun! 🏆\n\n"
            "**The following stats have been reset for everyone:**\n"
            "- 🏆 Wins\n"
            "- 🔫 Kills\n"
            "- 💥 Damage\n"
            "- 🎮 Matches Played\n\n"
            "Good luck to all players in Season 2! 🔁 It's a fresh start!"
        ),
        color=discord.Color.purple()
    )
    embed.set_footer(text="PUBG Discord Bot by ClashRanks")
    embed.timestamp = discord.utils.utcnow()

    await channel.send("@everyone", embed=embed)   
@bot.event
async def on_ready():
    print(f"{bot.user} s-a conectat cu succes!")
    if not check_for_wins.is_running():
        check_for_wins.start()

bot.run(TOKEN)
