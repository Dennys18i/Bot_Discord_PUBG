from data.constants import PUBG_API_KEY, USERNAMES, PLATFORM, DATA_FILE
import requests
from utils import save_data

def get_player_ids(player_ids, data):
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
        save_data(data, DATA_FILE)
    return player_ids