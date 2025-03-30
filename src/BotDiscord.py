import discord
from discord.ext import commands
from utils.load_data import load_data
from data.constants import CHANNEL_ID, TOKEN, DATA_FILE
from classes.pubg_bot_tasks import PubgBotTasks
import json
import os

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "data", "data.json")

data = load_data(DATA_FILE)

@bot.command()
async def leaderboard(ctx):
    scores_data = data.get("scores", {})

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
    damage_data = data.get("damage", {})
    player_match_count_data = data.get("player_match_count", {})

    if not damage_data:
        await ctx.send("Nu exista damage inregistrat!")
        return
    
    damage_per_match = {}
    for username, damage in damage_data.items():
        match_count = player_match_count_data.get(username, 1)  # Default la 1 dacă nu există date
        damage_per_match[username] = damage / match_count

    sorted_damages = sorted(damage_per_match.items(), key=lambda x: x[1], reverse=True)
    
    leaderboard_text = "🏆 **Leaderboard PUBG Damages** 🏆\n"
    
    for rank, (username, damage) in enumerate(sorted_damages, start=1):
        match_count = player_match_count_data.get(username, 1)
        leaderboard_text += f"{rank}. {username}: {damage:.2f} damage\n"
    
    await ctx.send(leaderboard_text)

@bot.command()
async def leaderboard_kills(ctx):
    kills_data = data.get("kills", {})

    if not kills_data:
        await ctx.send("Nu există kills înregistrate!")
        return
    
    sorted_kills = sorted(kills_data.items(), key=lambda x: x[1], reverse=True)
    
    leaderboard_text = "🏆 **Leaderboard PUBG Kills** 🏆\n"
    
    for rank, (username, kills) in enumerate(sorted_kills, start=1):
        leaderboard_text += f"{rank}. {username}: {kills} {'kill' if kills == 1 else 'kills'}\n"
    
    await ctx.send(leaderboard_text)

@bot.command()
async def leaderboard_sniper(ctx):
    longest_kill_data = data.get("longestKill", {})

    if not longest_kill_data:
        await ctx.send("Nu există încă longest kill-uri înregistrate.")
        return
    
    sorted_snipers = sorted(longest_kill_data.items(), key=lambda x: x[1], reverse=True)
    
    leaderboard_text = "🏆 **Leaderboard SniperMan** 🏆\n"
    
    for rank, (username, distance) in enumerate(sorted_snipers, start=1):
        leaderboard_text += f"{rank}. {username}: {distance} metri\n"
    
    await ctx.send(leaderboard_text)

@bot.event
async def on_ready():
    player_ids = data.get("playerIds", {})

    print(f"{bot.user} s-a conectat cu succes!")
    print(json.dumps(player_ids, indent=4))

    # initialize PubgBotTasks and automatically start the task loop
    PubgBotTasks(
        bot,
        CHANNEL_ID,
        data,
    )

bot.run(TOKEN)
