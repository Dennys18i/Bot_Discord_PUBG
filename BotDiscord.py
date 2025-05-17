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
bot = commands.Bot(command_prefix="!", intents=intents)

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

        if game_mode in ["arcade", "lab", "war", "bluebomb", "esportsmode", "gunplay_ibr", "ibr", "tdm", "tutorialatoz"] or match_type in ["custom", "tutorialatoz"]:
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

        update_data = {
            "$inc": {
                "damage": int(damage),
                "kills": int(kills),
                "matchCount": 1,
                "score": 1 if win_place == 1 else 0
            }
        }
        players_col.update_one({"username": username}, update_data)
        bot.loop.create_task(save_longest_kill(username, longest_kill))

        if win_place == 1:
            await channel.send(f"@everyone 🏆 {username} has won a match! Congratulations! 🎉")

        print(f"📊 {username} finished on the spot {win_place}, {kills} kills, {damage} damage")
        await asyncio.sleep(sleep_time)

@bot.command()
async def leaderboard(ctx):
    guild_id = ctx.guild.id
    top = list(players_col.find({"guild_id": guild_id}).sort("score", -1).limit(10))

    if not top:
        await ctx.send("There is no data")
        return

    msg = "🏆 **Leaderboard PUBG Wins** 🏆\n"
    for i, p in enumerate(top, start=1):
        msg += f"{i}. {p['username']}: {p['score']} win{'s' if p['score'] != 1 else ''}\n"
    await ctx.send(msg)

@bot.command()
async def leaderboard_damage(ctx):
    guild_id = ctx.guild.id
    players = list(players_col.find({"guild_id": guild_id}))

    if not players:
        await ctx.send("Nu există date.")
        return

    sorted_damages = sorted(players, key=lambda p: (p["damage"] / max(1, p["matchCount"])), reverse=True)
    msg = "🏆 **Leaderboard PUBG Damage/Match** 🏆\n"
    for i, p in enumerate(sorted_damages[:10], start=1):
        dmg = p["damage"] / max(1, p["matchCount"])
        msg += f"{i}. {p['username']}: {dmg:.2f} damage/match\n"
    await ctx.send(msg)

@bot.command()
async def leaderboard_kills(ctx):
    guild_id = ctx.guild.id
    top = list(players_col.find({"guild_id": guild_id}).sort("kills", -1).limit(10))

    msg = "🏆 **Leaderboard PUBG Kills** 🏆\n"
    for i, p in enumerate(top, start=1):
        msg += f"{i}. {p['username']}: {p['kills']} kills\n"
    await ctx.send(msg)

@bot.command()
async def leaderboard_sniper(ctx):
    guild_id = ctx.guild.id
    top = list(players_col.find({"guild_id": guild_id}).sort("longestKill", -1).limit(10))

    msg = "🏆 **Leaderboard SniperMan** 🏆\n"
    for i, p in enumerate(top, start=1):
        msg += f"{i}. {p['username']}: {p['longestKill']} m\n"
    await ctx.send(msg)

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

@bot.event
async def on_ready():
    print(f"{bot.user} s-a conectat cu succes!")
    if not check_for_wins.is_running():
        check_for_wins.start()

bot.run(TOKEN)
