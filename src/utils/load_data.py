import os
import json

def load_data(data_file):
    if os.path.exists(data_file):
        try:
            with open(data_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("Eroare la citirea damage.json, inițializăm un nou dicționar.")
            return {}
    return {}