from data.constants import PUBG_API_KEY, PLATFORM
import requests

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