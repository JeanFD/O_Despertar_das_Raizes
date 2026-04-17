import json, os
SAVE_DIR = "data/saves"

class SaveSystem:
    def __init__(self, game):
        self.game = game
        os.makedirs(SAVE_DIR, exist_ok=True)

    def save(self, slot, gameplay):
        p = gameplay.player
        data = {
            "position":  [p.pos.x, p.pos.y],
            "level":     gameplay.current_level_path,
            "abilities": dict(p.abilities),
            "health":    p.hp.current,
        }
        with open(f"{SAVE_DIR}/slot_{slot}.json", "w") as f:
            json.dump(data, f, indent=2)

    def load(self, slot):
        path = f"{SAVE_DIR}/slot_{slot}.json"
        if not os.path.exists(path):
            return None
        with open(path) as f:
            return json.load(f)