import discord
from discord.ext import commands, tasks
import requests
import json
import os
import asyncio

TOKEN = 'MTMzMzUwNjg5MDA3OTkzMjQ2OA.Gw7mw6.B3IV_iybP_AsZfmIMjrQkVJ0U-1x7JD-zu92Dc'
PUBG_API_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiI1YzhhYTY3MC1lMDBkLTAxM2QtNTcyZC03ZWRkNmY0MTRiOTUiLCJpc3MiOiJnYW1lbG9ja2VyIiwiaWF0IjoxNzQxNjMyMTU3LCJwdWIiOiJibHVlaG9sZSIsInRpdGxlIjoicHViZyIsImFwcCI6InRyYWNrLXB1Ymctd2luIn0.U1RvNG0Kuh26_3JMa0MTkpdfce9Dk4UkzmKDfRVhEhI"
CHANNEL_ID = 1329872665787240541

PLATFORM = "steam" 
USERNAMES = ["Dennyso01", "FutoZaurus", "AdolfRizzler696", "bularo", "monketv", "Moticel", "leggacys", "dany77777"]

sleep_time = 30

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Eroare la citirea damage.json, inițializăm un nou dicționar.")
            return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

data = load_data()
processed_matches = data.get("processedMatches", {})
damage_data = data.get("damage", {})
scores_data = data.get("scores", {})
kills_data = data.get("kills", {})
player_ids = data.get("playerIds", {})

def get_player_ids():
    headers = {"Authorization": f"Bearer {PUBG_API_KEY}", "Accept": "application/vnd.api+json"}
    for username in USERNAMES:
        if username in player_ids:
            continue
        url = f"https://api.pubg.com/shards/{PLATFORM}/players?filter[playerNames]={username}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200 and response.json()["data"]:
            player_ids[username] = response.json()["data"][0]["id"]

    if player_ids != data.get("playerIds", {}):
        data["playerIds"] = player_ids
        save_data(data)
    return player_ids

def filter_by_id(players, player_id):
    for player in players:
        if "type" in player and player["type"] == "participant" and player["attributes"]["stats"]["playerId"] == player_id:
            return player
    return None

def get_last_match(player_id):
    url = f"https://api.pubg.com/shards/{PLATFORM}/players/{player_id}"
    headers = {"Authorization": f"Bearer {PUBG_API_KEY}", "Accept": "application/vnd.api+json"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        
        
        matches = response.json()["data"]["relationships"]["matches"]["data"]
        
        if matches:
            last_match_id = matches[0]["id"]
            print(f"Ultimul meci al jucătorului {player_id}: {last_match_id}")
            return last_match_id
    
    return None

def get_player_info(player_id):
    last_match_id = get_last_match(player_id)
    if not last_match_id:
        return None

    if f"{player_id}:{last_match_id}" in processed_matches:
        print(f"Meciul {last_match_id} al jucătorului {player_id} a fost deja procesat. Se sare la următorul.")
        return None
    
    url = f"https://api.pubg.com/shards/{PLATFORM}/matches/{last_match_id}"
    headers = {"Authorization": f"Bearer {PUBG_API_KEY}", "Accept": "application/vnd.api+json"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        match_data = response.json()

        game_mode = match_data["data"]["attributes"]["gameMode"]
        print(f"Meci ID: {last_match_id} - Game Mode: {game_mode}")

        if game_mode in ["arcade", "lab", "war", "bluebomb", "esportsmode", "gunplay_ibr"]:
            print(f"Meciul {last_match_id} este {game_mode} și NU va fi luat în considerare.")
            return None
        
        filtered_player= filter_by_id(match_data["included"], player_id)
        if filtered_player and "winPlace" in filtered_player["attributes"]["stats"]:
            processed_matches[f"{player_id}:{last_match_id}"] = True
            data["processedMatches"] = processed_matches
            save_data(data)
            return filtered_player["attributes"]["stats"]

    return None

@tasks.loop(minutes=5)
async def check_for_wins():
    player_ids = get_player_ids()
    if not player_ids:
        print("Nu s-au putut obține ID-urile jucătorilor.")
        return
    
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        print("Canalul nu a fost găsit.")
        return
    
    for username, player_id in player_ids.items():
        stats = get_player_info(player_id)

        if not stats:
            print(f"Nu s-au putut obține informațiile sau meciul a fost deja procesat pentru jucătorul {username}.")
            continue

        win_place = stats["winPlace"]
        damage = stats["damageDealt"]
        kills = stats["kills"]

        if win_place == 1:
            scores_data[username] = scores_data.get(username, 0) + 1
            data["scores"] = scores_data
            save_data(data)

            await channel.send(f"@everyone 🏆 {username} a câștigat un meci! Felicitări! 🎉")
        elif win_place is not None:
            print(f"{username} a terminat pe locul {win_place}.")

        damage_data[username] = int(damage_data.get(username, 0) + damage)
        kills_data[username] = int(kills_data.get(username, 0) + kills)
        data["damage"] = damage_data
        data["kills"] = kills_data
        save_data(data)

        await asyncio.sleep(sleep_time)


@bot.command()
async def leaderboard(ctx):
    if not scores_data:
        await ctx.send("Nu există încă win-uri înregistrate.")
        return
    
    sorted_scores = sorted(scores_data.items(), key=lambda x: x[1], reverse=True)
    
    leaderboard_text = "🏆 **Leaderboard PUBG Wins** 🏆\n"
    
    for rank, (username, wins) in enumerate(sorted_scores, start=1):
        leaderboard_text += f"{rank}. {username}: {wins} victori{'i' if wins > 1 else 'e'}\n"
    
    await ctx.send(leaderboard_text)


@bot.command()
async def leaderboard_damage(ctx):
    if not damage_data:
        await ctx.send("Nu exista damage inregistrat!")
        return
    
    sorted_damages = sorted(damage_data.items(), key=lambda x: x[1], reverse=True)
    
    leaderboard_text = "🏆 **Leaderboard PUBG Damages** 🏆\n"
    
    for rank, (username, damage) in enumerate(sorted_damages, start=1):
        leaderboard_text += f"{rank}. {username}: {damage} damage\n"
    
    await ctx.send(leaderboard_text)

@bot.command()
async def leaderboard_kills(ctx):
    if not kills_data:
        await ctx.send("Nu există kills înregistrate!")
        return
    
    sorted_kills = sorted(kills_data.items(), key=lambda x: x[1], reverse=True)
    
    leaderboard_text = "🏆 **Leaderboard PUBG Kills** 🏆\n"
    
    for rank, (username, kills) in enumerate(sorted_kills, start=1):
        leaderboard_text += f"{rank}. {username}: {kills} {'kill' if kills == 1 else 'kills'}\n"
    
    await ctx.send(leaderboard_text)


@bot.event
async def on_ready():
    print(f"{bot.user} s-a conectat cu succes!")
    check_for_wins.start()

bot.run(TOKEN)
