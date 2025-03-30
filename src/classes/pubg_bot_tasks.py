from discord.ext import tasks
import asyncio
from utils.get_player_ids import get_player_ids
from utils.get_player_info import get_player_info
from utils.save_data import save_data
from data.constants import CHANNEL_ID, SLEEP_TIME, DATA_FILE

class PubgBotTasks:
    def __init__(self, bot, channel_id, data):
        self.bot = bot
        self.channel_id = channel_id
        self.data = data
        self.processed_matches = self.data.get("processedMatches", {})
        self.damage_data = self.data.get("damage", {})
        self.scores_data = self.data.get("scores", {})
        self.kills_data = self.data.get("kills", {})
        self.player_ids = self.data.get("playerIds", {})
        self.player_match_count_data = self.data.get("player_match_count", {})
        
        # Start loop only when bot is ready
        bot.loop.create_task(self.start_loop())

    @tasks.loop(minutes=5)
    async def check_for_wins(self):
        self.player_ids = get_player_ids(self.player_ids, self.data)
        if not self.player_ids:
            print("Nu s-au putut obține ID-urile jucătorilor.")
            return
        
        channel = self.bot.get_channel(CHANNEL_ID)
        if not channel:
            print("Canalul nu a fost găsit.")
            return
        
        for username, player_id in self.player_ids.items():
            stats = get_player_info(player_id, self.processed_matches, self.data, self.bot)

            if not stats:
                print(f"Nu s-au putut obține informațiile sau meciul a fost deja procesat pentru jucătorul {username}.")
                continue

            win_place = stats["winPlace"]
            damage = stats["damageDealt"]
            kills = stats["kills"]
            longest_kill = stats["longestKill"]

            if win_place == 1:
                self.scores_data[username] = self.scores_data.get(username, 0) + 1
                self.data["scores"] = self.scores_data
                save_data(self.data, DATA_FILE)

                await channel.send(f"@everyone 🏆 {username} a câștigat un meci! Felicitări! 🎉")
                print(f"{username} a terminat pe locul {win_place}.")
            elif win_place is not None:
                print(f"{username} a terminat pe locul {win_place}.")

            self.damage_data[username] = int(self.damage_data.get(username, 0) + damage)
            self.kills_data[username] = int(self.kills_data.get(username, 0) + kills)
            self.player_match_count_data[username] = int(self.player_match_count_data.get(username, 0) + 1)
            self.data["damage"] = self.damage_data
            self.data["kills"] = self.kills_data
            self.data["player_match_count"] = self.player_match_count_data
            save_data(self.data, DATA_FILE)

            await asyncio.sleep(SLEEP_TIME)

    @check_for_wins.before_loop
    async def before_check_for_wins(self):
        """Ensure the bot is ready before starting the loop."""
        await self.bot.wait_until_ready()