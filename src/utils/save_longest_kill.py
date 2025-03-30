from utils.save_data import save_data
from data.constants import CHANNEL_ID

async def save_longest_kill(username, distance, data, bot, longest_kill_data):

    global_record = data.get("globalLongestKill", {"username": None, "distance": 0})
    previous_record = global_record["distance"]
    channel = bot.get_channel(CHANNEL_ID)

    if username in longest_kill_data:
        if distance > longest_kill_data[username]:
            longest_kill_data[username] = distance
            data["longestKill"] = longest_kill_data
            save_data(data)
            print(f"Recordul pentru {username} a fost doborât! Noua distanță: {distance} metri.")
    else:
        longest_kill_data[username] = distance
        data["longestKill"] = longest_kill_data
        save_data(data)

    if distance > previous_record:
        data["globalLongestKill"] = {"username": username, "distance": distance}
        save_data(data)
        await channel.send(f"🎯 **NOU RECORD!** 🎯\n{username} a reușit un kill de la **{distance} metri**! 🚀🥇")
        print(f"NOU RECORD GLOBAL: {username} - {distance} metri!")