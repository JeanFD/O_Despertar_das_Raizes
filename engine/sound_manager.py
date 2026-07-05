import pygame
import os


class SoundManager:

    def __init__(self, sfx_volume=1.0, music_volume=0.5):
        pygame.mixer.init()

        self.sfx = {}                     
        self.sfx_volume = sfx_volume
        self.music_volume = music_volume
        self.current_music = None

        pygame.mixer.music.set_volume(self.music_volume)



    def load_sfx(self, name, path):
        if not os.path.exists(path):
            print(f"[SoundManager] Aviso: arquivo não encontrado -> {path}")
            return
        sound = pygame.mixer.Sound(path)
        sound.set_volume(self.sfx_volume)
        self.sfx[name] = sound

    def load_sfx_batch(self, mapping):
        for name, path in mapping.items():
            self.load_sfx(name, path)

    def play(self, name):
        sound = self.sfx.get(name)
        if sound:
            sound.play()
        else:
            print(f"[SoundManager] Aviso: som '{name}' não carregado")

    def set_sfx_volume(self, volume):
        self.sfx_volume = volume
        for sound in self.sfx.values():
            sound.set_volume(volume)



    def play_music(self, path, loop=True, fade_ms=500):
        if self.current_music == path:
            return 
        if not os.path.exists(path):
            print(f"[SoundManager] Aviso: música não encontrada -> {path}")
            return

        pygame.mixer.music.load(path)
        pygame.mixer.music.play(-1 if loop else 0, fade_ms=fade_ms)
        self.current_music = path

    def stop_music(self, fade_ms=500):
        pygame.mixer.music.fadeout(fade_ms)
        self.current_music = None

    def set_music_volume(self, volume):
        self.music_volume = volume
        pygame.mixer.music.set_volume(volume)