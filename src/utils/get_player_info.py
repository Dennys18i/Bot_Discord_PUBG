from data.constants import PUBG_API_KEY, PLATFORM, DATA_FILE
# from utils import save_data, get_last_match, filter_by_id
from utils.get_last_match import get_last_match
from utils.filter_by_id import filter_by_id
from utils.save_data import save_data
from utils.save_longest_kill import save_longest_kill
import requests

def get_player_info(player_id, processed_matches, data, bot):
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
        match_type = match_data["data"]["attributes"].get("matchType", "")
        print(f"Meci ID: {last_match_id} - Game Mode: {game_mode}")

        if game_mode not in ["solo", "solo-fpp", "duo", "duo-fpp", "squad", "squad-fpp"] or match_type == "custom":
            print(f"Meciul {last_match_id} este {game_mode} și NU va fi luat în considerare.")
            return None
        
        filtered_player= filter_by_id(match_data["included"], player_id)
        if filtered_player and "winPlace" in filtered_player["attributes"]["stats"]:
            processed_matches[f"{player_id}:{last_match_id}"] = True
            data["processedMatches"] = processed_matches
            save_data(data, DATA_FILE)

            if "longestKill" in filtered_player["attributes"]["stats"]:
                distance = filtered_player["attributes"]["stats"]["longestKill"]
                bot.loop.create_task(save_longest_kill(filtered_player["attributes"]["stats"]["name"], distance))

            return filtered_player["attributes"]["stats"]

    return None