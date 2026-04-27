import pygame 
import math

C_BG = (20, 8, 22)
C_PANEL = (22, 18, 40)
C_PANEL_EDGE = (50, 40, 90)
C_TEXT = (210, 205, 220)
C_TEXT_DIM = (100, 95,120)
C_HIGHLIGHT = (140, 110, 225)
C_HIGHLIGHT_BG = (40, 30, 80)
C_ACCENT = (255, 200, 80)
C_BAR_BG = (40, 35, 60)
C_BAR_FILL = (140, 110, 255)
C_DANGER = (255, 80, 80)
C_SUCCESS = (80, 220, 130)

def draw_gradient_bg(surface):
    w, h = surface.get_size()
    for y in range(h):
        t = y / h
        r = int(10 + 8 * t)
        g = int( 8 + 5 * t)
        b = int(22 + 15 * t)
        pygame.draw.line(surface, (r, g, b), (0, y), (w, y))

def draw_panel(surface, rect, alpha=220):
    panel = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    panel.fill((*C_PANEL, alpha))
    pygame.draw.rect(panel, (*C_PANEL_EDGE, alpha), (0, 0, rect.w, rect.h), 2, border_radius=8)
    surface.blit(panel, rect.topleft)

def draw_title(surface, text: str, y: int, size: int = 40, color=None):
    font = pygame.font.SysFont("consolas,monospace", size, bold=True)
    shadow = font.render(text, True, (0, 0, 0))
    main = font.render(text, True, color or C_ACCENT)
    cx = surface.get_width() // 2
    surface.blit(shadow, (cx - shadow.get_width() // 2 + 2, y + 2))
    surface.blit(main, (cx - main.get_width() // 2, y))

def draw_menu_items(surface, items: list[str], selected: int, x: int, y: int, spacing: int = 44, size: int =22, center: bool = True, colors: list = None):
    font = pygame.font.SysFont("consolas,monospace", size)
    rects = []
    sw = surface.get_width()

    for i, text in enumerate(items):
        is_sel = (i == selected)
        color = colors[i] if colors else (C_HIGHLIGHT if is_sel else C_TEXT)

        label = font. render(text, True, color)
        if center:
            lx = sw // 2 - label.get_width() // 2
        else: 
            lx = x
        
        ly = y + i * spacing
        item_rect = pygame.Rect(lx - 16, ly -4, label.get_width() + 32, spacing - 8)
        rects.append(item_rect)

        if is_sel:
            pygame.draw.rect(surface, C_HIGHLIGHT_BG, item_rect, border_radius = 6)
            pygame.draw.rect(surface, C_HIGHLIGHT, item_rect, 1, border_radius = 6)

            t = pygame.time.get_ticks() / 400
            offset = int(math.sin(t) * 4)
            arrow = font.render(">", True, C_ACCENT)
            surface.blit(arrow, (item_rect.left - 20 + offset, ly))

        surface.blit(label, (lx, ly))

    return rects

def draw_slider(surface, x: int, y: int, w: int, value: float, label: str, selected: bool = False):
    font = pygame.font.SysFont("consolas,monospace", 20)
    color = C_HIGHLIGHT if selected else C_TEXT

    lbl = font.render(label, True, color)
    surface.blit(lbl, (x, y))

    bar_x = x + 200
    bar_w = w - 200 - 60
    bar_h = 12
    bar_y = y + 6
    pygame.draw.rect(surface, C_BAR_BG, (bar_x, bar_y, bar_w, bar_h), border_radius = 4)
    fill_w = int(bar_w * max(0, min(1, value)))
    if fill_w > 0:
        pygame.draw. rect(surface, C_BAR_FILL if selected else C_TEXT_DIM, (bar_x, bar_y, fill_w, bar_h), border_radius = 4)
    pygame.draw.rect(surface, color, (bar_x, bar_y, bar_w, bar_h), 1, border_radius=4)

    pct = font.render(f"{int(value * 100)}%", True, color)
    surface.blit(pct, (bar_x + bar_w + 10, y))

def draw_toggle(surface, x: int, y: int, value: bool, label: str, selected: bool = False):
    font = pygame.font.SysFont("consolas, monospace", 20)
    color = C_HIGHLIGHT if selected else C_TEXT

    lbl = font.render(label, True, color)
    surface.blit(lbl, (x, y))

    val_text = "ON" if value else "OFF"
    val_color = C_SUCCESS if value else C_DANGER
    val_surf =font.render(val_text, True, val_color)
    surface.blit(val_surf, (x + 200, y ))

def draw_hint_bar(surface, hints: str):
    font = pygame.font.SysFont("consolas,monospace", 14)
    h = surface.get_height()
    txt = font.render(hints, True, C_TEXT_DIM)
    surface.blit(txt, (surface.get_width() // 2 - txt.get_width() // 2, h - 30))

def draw_particles(surface, tick: int):
    for i in range(12):
        seed = i * 137
        speed = 0.3 + (seed % 7) * 0.1
        x = (seed * 3 + tick * speed) % surface.get_width()
        y = (seed * 7 + tick * speed * 0.5) % surface.get_height()
        r = 1 + (seed % 3)
        alpha = 30 + (seed % 40)
        color = (C_HIGHLIGHT[0], C_HIGHLIGHT[1], C_HIGHLIGHT[2])
        s = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        pygame.draw.circle(s, (*color, alpha), (r, r), r)
        surface.blit(s, (int(x), int(y)))