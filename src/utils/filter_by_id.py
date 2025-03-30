def filter_by_id(players, player_id):
    for player in players:
        if "type" in player and player["type"] == "participant" and player["attributes"]["stats"]["playerId"] == player_id:
            return player
    return None