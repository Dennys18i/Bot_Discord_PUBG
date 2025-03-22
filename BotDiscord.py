import discord
from discord.ext import commands, tasks
import requests
import json
import os
import asyncio

TOKEN = 'MTMzMzUwNjg5MDA3OTkzMjQ2OA.Gw7mw6.B3IV_iybP_AsZfmIMjrQkVJ0U-1x7JD-zu92Dc'
PUBG_API_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJqdGkiOiI1YzhhYTY3MC1lMDBkLTAxM2QtNTcyZC03ZWRkNmY0MTRiOTUiLCJpc3MiOiJnYW1lbG9ja2VyIiwiaWF0IjoxNzQxNjMyMTU3LCJwdWIiOiJibHVlaG9sZSIsInRpdGxlIjoicHViZyIsImFwcCI6InRyYWNrLXB1Ymctd2luIn0.U1RvNG0Kuh26_3JMa0MTkpdfce9Dk4UkzmKDfRVhEhI"
PLATFORM = "steam" 
USERNAMES = ["Dennyso01", "FutoZaurus", "AdolfRizzler696", "bularo", "monketv", "Moticel", "leggacys", "dany77777"]  
CHANNEL_ID = 1329872665787240541
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

processed_matches_file = "processed_matches.json"

# Încărcare meciuri procesate
def load_processed_matches():
    if os.path.exists(processed_matches_file):
        try:
            with open(processed_matches_file, "r", encoding="utf-8") as f:
                # Încercăm să citim fișierul ca JSON
                return json.load(f)
        except json.JSONDecodeError:
            print("Eroare la decodificarea fișierului JSON. Fișierul este corupt sau are un format invalid.")
            return {}  # Returnează un dicționar gol dacă fișierul este corupt
    else:
        print(f"Fișierul {processed_matches_file} nu există. Se va crea unul nou.")
        return {}  # Dacă fișierul nu există, returnează un dicționar gol

# Salvare meciuri procesate
def save_processed_matches(matches):
    with open(processed_matches_file, "w", encoding="utf-8") as f:
        json.dump(matches, f, indent=4)

processed_matches = load_processed_matches()

def get_player_ids():
    player_ids = {}
    headers = {"Authorization": f"Bearer {PUBG_API_KEY}", "Accept": "application/vnd.api+json"}
    for username in USERNAMES:
        url = f"https://api.pubg.com/shards/{PLATFORM}/players?filter[playerNames]={username}"
        response = requests.get(url, headers=headers)
        if response.status_code == 200 and response.json()["data"]:
            player_ids[username] = response.json()["data"][0]["id"]
    return player_ids

def filter_by_id(players, player_id):
    for player in players:
        if "type" in player and player["type"] == "participant" and player["attributes"]["stats"]["playerId"] == player_id:
            return player
    return None

# Încărcare scoruri din fișier
scores_file = "scores.json"
try:
    with open(scores_file, "r", encoding="utf-8") as f:
        scores = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    scores = {}

def get_last_match(player_id):
    url = f"https://api.pubg.com/shards/{PLATFORM}/players/{player_id}"
    headers = {"Authorization": f"Bearer {PUBG_API_KEY}", "Accept": "application/vnd.api+json"}
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        
        # print(f"Răspuns pentru player_id {player_id}: {response.json()}")
        matches = response.json()["data"]["relationships"]["matches"]["data"]
        
        if matches:
            last_match_id = matches[0]["id"]
            print(f"Ultimul meci al jucătorului {player_id}: {last_match_id}")
            return last_match_id
    return None

def get_player_rank(player_id):
    last_match_id = get_last_match(player_id)
    if not last_match_id:
        return None
    
    # Verifică dacă meciul a fost deja procesat
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
        
        filtered_player = filter_by_id(match_data["included"], player_id)
        if filtered_player and "winPlace" in filtered_player["attributes"]["stats"]:
            # Adăugăm meciul la lista de meciuri procesate
            processed_matches[f"{player_id}:{last_match_id}"] = True
            save_processed_matches(processed_matches)
            return filtered_player["attributes"]["stats"]["winPlace"]
            
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
        win_place = get_player_rank(player_id)
        if win_place == 1:
            scores[username] = scores.get(username, 0) + 1
            with open(scores_file, "w", encoding="utf-8") as f:
             json.dump(scores, f, indent=4)

            await channel.send(f"@everyone 🏆 {username} a câștigat un meci! Felicitări! 🎉")
        elif win_place is not None:
            print(f"{username} a terminat pe locul {win_place}.")
        
        await asyncio.sleep(30)

# @bot.command()
# async def leaderboard(ctx):
#     data = load_data()
#     sorted_players = sorted(data.items(), key=lambda x: x[1], reverse=True)
    
#     if not sorted_players:
#         await ctx.send("Nu există încă win-uri înregistrate.")
#         return
    
#     leaderboard_text = "🏆 **Leaderboard PUBG Wins** 🏆\n"
#     for winPlace, (player, wins) in enumerate(sorted_players, start=1):
#         if player != "checked_matches":  
#             leaderboard_text += f"{winPlace}. {player}: {wins} win-uri\n"
    
#     await ctx.send(leaderboard_text)

@bot.command()
async def leaderboard(ctx):
    if not scores:
        await ctx.send("Nu există încă win-uri înregistrate.")
        return
    
    # Sortăm scorurile în ordine descrescătoare
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    
    leaderboard_text = "🏆 **Leaderboard PUBG Wins** 🏆\n"
    
    # Afișăm top 10 jucători
    for rank, (username, wins) in enumerate(sorted_scores, start=1):
        leaderboard_text += f"{rank}. {username}: {wins} victorie{'i' if wins > 1 else ''}\n"
    
    await ctx.send(leaderboard_text)

#bun
# @bot.command()
# async def winPlace(ctx, username: str):
#     player_ids = get_player_ids()
#     if username not in player_ids:
#         await ctx.send(f"Jucătorul {username} nu a fost găsit.")
#         return
    
#     player_id = player_ids[username]
#     winPlace = get_player_rank(player_id)
    
#     if winPlace:
#         await ctx.send(f"{username} a obținut locul {winPlace} în ultimul meci!")
#         if winPlace == 4:
#             scores[username] = scores.get(username, 0) + 1
#             with open(scores_file, "w", encoding="utf-8") as f:
#              json.dump(scores, f, indent=4)
#             await ctx.send(f"Felicitări {username}, ai obținut locul 4! 🎉 Acum ai {scores[username]} puncte.")
#     else:
#        await ctx.send(f"Nu s-a putut obține locul pentru {username} în ultimul meci.")


@bot.event
async def on_ready():
    print(f"{bot.user} s-a conectat cu succes!")
    check_for_wins.start()

bot.run(TOKEN)








