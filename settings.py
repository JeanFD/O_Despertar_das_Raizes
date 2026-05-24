TITLE    = "O Despertar das Raízes"
SCREEN_W = 1280
SCREEN_H = 720
FPS      = 60
FIXED_DT = 1.0 / 60.0
MAX_STEPS = 8

GRAVITY = 1800
MAX_FALL = 900

HOST_PORT = 7777
CLIENT_PORT = 7778
NET_TIMEOUT = 5.0

# Matchmaker da arquitetura 2.0 (servidor dedicado em VPS).
# Em dev: http://127.0.0.1:8080. Em produção: https://<seu-dominio>.
MATCHMAKER_URL = "http://127.0.0.1:8080"