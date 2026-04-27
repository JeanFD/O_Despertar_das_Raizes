import json, os

SETTINGS_PATH = "data/settings.json"

DEFAULTS = {
    "master_volume": 0.7,
    "music_volume": 0.5,
    "sfx_volume": 0.8,
    "fullscreen": False,
    "screen_shake": True,
    "show_fps": False,
    "last_save_slot": -1
}

class SettingsManager:
    def __init__(self):
        self._data = dict(DEFAULTS)
        self._load()

    def get(self, key: str):
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value):
        self._data[key] = value

    def toggle(self, key: str):
        self._data[key] = not self._data.get(key, False)

    def cycle(self, key: str, step: float, lo: float, hi: float):
        v = self._data.get(key, lo) + step
        if v > hi + 0.001:
            v = lo
        elif v < lo - 0.001:
            v = hi
        self._data[key] = round(v, 2)

    def save(self):
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok = True)
        with open(SETTINGS_PATH, "w") as f:
            json.dump(self._data, f, indent=2)

    def _load(self):
        if os.path.exists(SETTINGS_PATH):
            try:
                with open(SETTINGS_PATH) as f:
                    loaded = json.load(f)
                self._data.update(loaded)
            except (json.JSONDecodeError, IOError):
                pass

    def apply_audio(self):
        import pygame
        try:
            pygame.mixer.music.set_volume(
                self.get("music_volume") * self.get("master_volume")
            )
        except Exception:
            pass
    