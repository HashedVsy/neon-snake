"""
NEON SNAKE - Pygame Community Edition (Browser & Desktop)
=========================================================
A complete Snake game built with Pygame Community Edition (pygame-ce).
Includes Solo Mode, Local 2-Player Versus, and Player vs CPU Bot!

Controls:
  Solo Mode:
    - Arrow Keys or W / A / S / D : Move
  2-Player Versus:
    - Player 1 (Cyan)   : Arrow Keys (Up, Down, Left, Right)
    - Player 2 (Magenta): W, A, S, D
  Versus CPU Bot:
    - Player 1 (Cyan)   : Arrow Keys or W / A / S / D
    - Player 2 (Magenta): CPU AI Bot
  General:
    - 1, 2, 3 or M      : Switch Game Mode (Solo / 2P Versus / Vs CPU)
    - SPACE or ENTER    : Start / Restart Round
    - P or ESC          : Pause / Resume
    - R                 : Quick Reset
"""

import sys
import os
import io
import time
import json
import random
import math
import struct
import argparse
import asyncio
import socket
import threading
import hashlib
import base64
import collections
import zipfile
import webbrowser
import http.server
import socketserver
import urllib.parse

# Set SDL dummy driver if running in headless/browser mode and not on Emscripten/Desktop
RUNNING_IN_BROWSER_MODE = ("--desktop" not in sys.argv and "--window" not in sys.argv and sys.platform != "emscripten")
if RUNNING_IN_BROWSER_MODE:
    os.environ["SDL_VIDEODRIVER"] = "dummy"

import pygame

# ---------------------------------------------------------
# CONSTANTS & CONFIGURATION
# ---------------------------------------------------------
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
GRID_SIZE = 20
GRID_COLS = WINDOW_WIDTH // GRID_SIZE   # 40 cols (0..39)
GRID_ROWS = WINDOW_HEIGHT // GRID_SIZE  # 30 rows (0..29)

# HUD Bar occupies rows 0 and 1 (0 to 39px).
# Playable grid strictly starts at row 2 (y = 40px) to prevent apples being shadowed.
PLAY_ROW_START = 2
HUD_HEIGHT = PLAY_ROW_START * GRID_SIZE  # 40px

# Colors (Modern Neon Palette - Zero Emojis)
COLOR_BG_DARK = (13, 17, 23)
COLOR_GRID_LINE = (22, 27, 34)
COLOR_HUD_LINE = (0, 240, 255)

# Player 1 (Cyan / Emerald)
COLOR_P1_HEAD = (0, 240, 255)
COLOR_P1_BODY_1 = (0, 230, 118)
COLOR_P1_BODY_2 = (0, 176, 255)

# Player 2 / Bot (Magenta / Coral / Gold)
COLOR_P2_HEAD = (255, 42, 109)
COLOR_P2_BODY_1 = (255, 117, 151)
COLOR_P2_BODY_2 = (255, 183, 3)

COLOR_EYE_WHITE = (255, 255, 255)
COLOR_EYE_PUPIL = (10, 15, 20)

COLOR_FOOD_APPLE = (255, 59, 48)       # Neon Red
COLOR_FOOD_STEM = (76, 217, 100)
COLOR_FOOD_GOLDEN = (255, 215, 0)      # Golden Yellow
COLOR_TEXT_PRIMARY = (240, 246, 252)
COLOR_TEXT_MUTED = (139, 148, 158)
COLOR_TEXT_ACCENT = (255, 215, 0)
COLOR_DANGER = (255, 69, 58)

HIGH_SCORE_FILE = "highscore.json"


# ---------------------------------------------------------
# GAME MODES & STATES
# ---------------------------------------------------------
class GameMode:
    SOLO = "SOLO"
    PVP = "PVP"     # 2 Players Local (P1 Arrows vs P2 WASD)
    BOT = "BOT"     # Player vs CPU Bot


class GameState:
    START = "START"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    GAME_OVER = "GAME_OVER"


# ---------------------------------------------------------
# SOUND MANAGER (Procedural Retro Audio - Zero External Files)
# ---------------------------------------------------------
class RetroSoundManager:
    """Generates 8-bit procedural sound effects in-memory using pygame.mixer."""
    def __init__(self):
        self.sounds = {}
        self.enabled = False
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            self.enabled = True
            self._generate_sounds()
        except Exception:
            self.enabled = False

    def _generate_tone(self, freq_start, freq_end, duration, volume=0.25):
        sample_rate = 44100
        n_samples = int(sample_rate * duration)
        buf = bytearray()
        for i in range(n_samples):
            t = i / sample_rate
            progress = i / max(1, n_samples)
            freq = freq_start + (freq_end - freq_start) * progress
            env = 1.0 - progress
            if i < 150:
                env *= (i / 150)
            sample_val = int(32767 * volume * env * math.sin(2 * math.pi * freq * t))
            buf.extend(struct.pack("<h", sample_val))
        return pygame.mixer.Sound(buffer=bytes(buf))

    def _generate_sounds(self):
        try:
            self.sounds["eat"] = self._generate_tone(440, 880, 0.08, volume=0.25)
            self.sounds["golden"] = self._generate_tone(600, 1200, 0.18, volume=0.3)
            self.sounds["die"] = self._generate_tone(300, 80, 0.28, volume=0.35)
            self.sounds["start"] = self._generate_tone(350, 700, 0.12, volume=0.25)
        except Exception:
            self.enabled = False

    def play(self, name):
        if self.enabled and name in self.sounds:
            try:
                self.sounds[name].play()
            except Exception:
                pass


# ---------------------------------------------------------
# PARTICLE SYSTEM
# ---------------------------------------------------------
class Particle:
    def __init__(self, x, y, color):
        self.x = float(x)
        self.y = float(y)
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(1.5, 4.5)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.color = color
        self.life = random.randint(18, 30)
        self.max_life = self.life
        self.radius = random.uniform(2.5, 4.5)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.95
        self.vy *= 0.95
        self.life -= 1
        return self.life > 0

    def draw(self, surface):
        if self.life > 0:
            alpha_ratio = self.life / self.max_life
            r = max(1, int(self.radius * alpha_ratio))
            pygame.draw.circle(surface, self.color, (int(self.x), int(self.y)), r)


# ---------------------------------------------------------
# CPU AI BOT (Intelligent Pathfinding with Obstacle Avoidance)
# ---------------------------------------------------------
def get_bot_next_move(bot_head, bot_body, other_snake, foods, current_dir):
    obstacles = set(bot_body).union(set(other_snake))
    valid_dirs = [(0, -1), (0, 1), (-1, 0), (1, 0)]
    opposite = (-current_dir[0], -current_dir[1])

    # Filter out direct 180° reversal
    allowed_dirs = [d for d in valid_dirs if d != opposite]

    # Helper: check bounds and obstacles
    def is_safe(pos):
        x, y = pos
        return 0 <= x < GRID_COLS and PLAY_ROW_START <= y < GRID_ROWS and pos not in obstacles

    # Helper: flood-fill to avoid dead ends
    def count_open_space(start_pos, limit=16):
        visited = {start_pos}
        q = collections.deque([start_pos])
        count = 0
        while q and count < limit:
            cx, cy = q.popleft()
            count += 1
            for dx, dy in valid_dirs:
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < GRID_COLS and PLAY_ROW_START <= ny < GRID_ROWS:
                    if (nx, ny) not in obstacles and (nx, ny) not in visited:
                        visited.add((nx, ny))
                        q.append((nx, ny))
        return count

    # 1. BFS to nearest apple
    queue = collections.deque([(bot_head, [])])
    visited = {bot_head}
    food_set = set(foods)
    best_step = None

    while queue:
        curr, path = queue.popleft()
        if curr in food_set and path:
            best_step = path[0]
            break
        for dx, dy in allowed_dirs if curr == bot_head else valid_dirs:
            nx, ny = curr[0] + dx, curr[1] + dy
            if is_safe((nx, ny)) and (nx, ny) not in visited:
                visited.add((nx, ny))
                queue.append(((nx, ny), path + [(dx, dy)]))

    # If BFS path found, ensure it doesn't lead directly into an enclosed trap
    if best_step:
        next_pos = (bot_head[0] + best_step[0], bot_head[1] + best_step[1])
        if count_open_space(next_pos) >= min(8, len(bot_body)):
            return best_step

    # 2. Fallback: select move with the most open space
    best_dir = current_dir
    max_space = -1
    for dx, dy in allowed_dirs:
        nx, ny = bot_head[0] + dx, bot_head[1] + dy
        if is_safe((nx, ny)):
            space = count_open_space((nx, ny))
            if space > max_space:
                max_space = space
                best_dir = (dx, dy)

    return best_dir


# ---------------------------------------------------------
# CORE SNAKE GAME ENGINE
# ---------------------------------------------------------
class SnakeGame:
    def __init__(self):
        pygame.init()
        pygame.font.init()

        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("Neon Snake - Pygame Community Edition")
        self.clock = pygame.time.Clock()

        # Fonts
        self.font_large = pygame.font.Font(None, 60)
        self.font_medium = pygame.font.Font(None, 32)
        self.font_small = pygame.font.Font(None, 22)

        self.sound_mgr = RetroSoundManager()
        self.high_score = self.load_high_score()

        # Mode configuration
        self.mode = GameMode.SOLO
        self.language = "en"
        self.p1_wins = 0
        self.p2_wins = 0

        # Pre-render crystal clear high-contrast grid
        self.grid_surface = self._create_grid_surface()

        self.reset_game()
        self.state = GameState.START

        # Frame capture for web streaming
        self.latest_frame_bytes = b""
        self.frame_lock = threading.Lock()
        self.input_queue = []
        self.stats = {}

    def load_high_score(self):
        # Persistent browser scores are managed by client-side localStorage.
        return 0

    def save_high_score(self):
        # Kept as a compatibility hook for the game loop; no file is written.
        return

    def set_browser_high_score(self, value):
        try:
            self.high_score = max(self.high_score, int(value))
        except (TypeError, ValueError):
            pass

    def set_language(self, value):
        self.language = "de" if str(value).lower() == "de" else "en"

    def reset_game(self):
        mid_y = (GRID_ROWS + PLAY_ROW_START) // 2

        # Player 1 (Left Side, Moving Right)
        if self.mode == GameMode.SOLO:
            p1_start_x = GRID_COLS // 2
        else:
            p1_start_x = 10

        self.p1_snake = [
            (p1_start_x, mid_y),
            (p1_start_x - 1, mid_y),
            (p1_start_x - 2, mid_y),
            (p1_start_x - 3, mid_y),
        ]
        self.p1_dir = (1, 0)
        self.p1_queue = []
        self.p1_score = 0
        self.p1_apples = 0

        # Player 2 / Bot (Right Side, Moving Left)
        p2_start_x = GRID_COLS - 11
        self.p2_snake = [
            (p2_start_x, mid_y),
            (p2_start_x + 1, mid_y),
            (p2_start_x + 2, mid_y),
            (p2_start_x + 3, mid_y),
        ]
        self.p2_dir = (-1, 0)
        self.p2_queue = []
        self.p2_score = 0
        self.p2_apples = 0

        self.base_speed = 11.5
        self.current_speed = self.base_speed

        # Food array: 1 apple in solo, 2 apples in versus mode for high action
        self.foods = []
        self.golden_food = None
        self.golden_timer = 0
        num_foods = 2 if self.mode != GameMode.SOLO else 1
        for _ in range(num_foods):
            self.spawn_food()

        self.particles = []
        self.death_reason = ""
        self.winner = None
        self.is_new_high_score = False

        self.move_accumulator = 0.0
        self.pulse_phase = 0.0

    def get_all_occupied_cells(self):
        occupied = set(self.p1_snake)
        if self.mode != GameMode.SOLO:
            occupied.update(self.p2_snake)
        occupied.update(self.foods)
        if self.golden_food:
            occupied.add(self.golden_food)
        return occupied

    def spawn_food(self):
        """Spawns food strictly below the HUD bar (y >= PLAY_ROW_START)."""
        occupied = self.get_all_occupied_cells()
        available = [
            (x, y)
            for x in range(GRID_COLS)
            for y in range(PLAY_ROW_START, GRID_ROWS)
            if (x, y) not in occupied
        ]
        if available:
            new_apple = random.choice(available)
            self.foods.append(new_apple)

    def spawn_golden_food(self):
        occupied = self.get_all_occupied_cells()
        available = [
            (x, y)
            for x in range(GRID_COLS)
            for y in range(PLAY_ROW_START, GRID_ROWS)
            if (x, y) not in occupied
        ]
        if available:
            self.golden_food = random.choice(available)
            self.golden_timer = 60 * 10

    def queue_key_event(self, key_code):
        self.input_queue.append(key_code)

    def handle_input(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            elif event.type == pygame.KEYDOWN:
                self.process_key_action(event.key)

        while self.input_queue:
            raw_key = self.input_queue.pop(0)
            mapped_key = self.map_web_key(raw_key)
            if mapped_key is not None:
                self.process_key_action(mapped_key)

    def map_web_key(self, web_key):
        mapping = {
            "ArrowUp": pygame.K_UP,
            "KeyW": pygame.K_w,
            "ArrowDown": pygame.K_DOWN,
            "KeyS": pygame.K_s,
            "ArrowLeft": pygame.K_LEFT,
            "KeyA": pygame.K_a,
            "ArrowRight": pygame.K_RIGHT,
            "KeyD": pygame.K_d,
            "Space": pygame.K_SPACE,
            "Enter": pygame.K_RETURN,
            "KeyP": pygame.K_p,
            "Escape": pygame.K_ESCAPE,
            "KeyR": pygame.K_r,
            "KeyM": pygame.K_m,
            "Digit1": pygame.K_1,
            "Digit2": pygame.K_2,
            "Digit3": pygame.K_3,
            "UP": pygame.K_UP,
            "DOWN": pygame.K_DOWN,
            "LEFT": pygame.K_LEFT,
            "RIGHT": pygame.K_RIGHT,
            "RESTART": pygame.K_SPACE,
            "PAUSE": pygame.K_p,
        }
        return mapping.get(web_key, None)

    def cycle_mode(self, specific_mode=None):
        if specific_mode:
            self.mode = specific_mode
        else:
            order = [GameMode.SOLO, GameMode.PVP, GameMode.BOT]
            idx = order.index(self.mode)
            self.mode = order[(idx + 1) % len(order)]
        self.p1_wins = 0
        self.p2_wins = 0
        self.reset_game()
        self.state = GameState.START

    def process_key_action(self, key):
        # Mode Selection Keys (1, 2, 3 or M)
        if key == pygame.K_m:
            self.cycle_mode()
            return
        elif key == pygame.K_1:
            self.cycle_mode(GameMode.SOLO)
            return
        elif key == pygame.K_2:
            self.cycle_mode(GameMode.PVP)
            return
        elif key == pygame.K_3:
            self.cycle_mode(GameMode.BOT)
            return

        if self.state == GameState.START:
            if key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_UP, pygame.K_w,
                       pygame.K_DOWN, pygame.K_s, pygame.K_LEFT, pygame.K_a,
                       pygame.K_RIGHT, pygame.K_d):
                self.state = GameState.PLAYING
                self.sound_mgr.play("start")

        elif self.state == GameState.PLAYING:
            if key in (pygame.K_p, pygame.K_ESCAPE):
                self.state = GameState.PAUSED
                return
            elif key == pygame.K_r:
                self.reset_game()
                self.state = GameState.PLAYING
                return

            # PLAYER 1 CONTROLS:
            # In Solo / Vs CPU: Arrow keys or WASD control P1.
            # In 2P Versus: Arrow keys control P1, WASD controls P2.
            p1_turn = None
            if key == pygame.K_UP or (self.mode != GameMode.PVP and key == pygame.K_w):
                p1_turn = (0, -1)
            elif key == pygame.K_DOWN or (self.mode != GameMode.PVP and key == pygame.K_s):
                p1_turn = (0, 1)
            elif key == pygame.K_LEFT or (self.mode != GameMode.PVP and key == pygame.K_a):
                p1_turn = (-1, 0)
            elif key == pygame.K_RIGHT or (self.mode != GameMode.PVP and key == pygame.K_d):
                p1_turn = (1, 0)

            if p1_turn:
                ref = self.p1_queue[-1] if self.p1_queue else self.p1_dir
                if (p1_turn[0] != -ref[0] or p1_turn[1] != -ref[1]) and p1_turn != ref:
                    if len(self.p1_queue) < 2:
                        self.p1_queue.append(p1_turn)
                        interval = 1.0 / self.current_speed
                        if self.move_accumulator > interval * 0.35:
                            self.move_accumulator = interval

            # PLAYER 2 CONTROLS (Only in 2P Versus mode)
            if self.mode == GameMode.PVP:
                p2_turn = None
                if key == pygame.K_w:
                    p2_turn = (0, -1)
                elif key == pygame.K_s:
                    p2_turn = (0, 1)
                elif key == pygame.K_a:
                    p2_turn = (-1, 0)
                elif key == pygame.K_d:
                    p2_turn = (1, 0)

                if p2_turn:
                    ref2 = self.p2_queue[-1] if self.p2_queue else self.p2_dir
                    if (p2_turn[0] != -ref2[0] or p2_turn[1] != -ref2[1]) and p2_turn != ref2:
                        if len(self.p2_queue) < 2:
                            self.p2_queue.append(p2_turn)
                            interval = 1.0 / self.current_speed
                            if self.move_accumulator > interval * 0.35:
                                self.move_accumulator = interval

        elif self.state == GameState.PAUSED:
            if key in (pygame.K_p, pygame.K_ESCAPE, pygame.K_SPACE, pygame.K_RETURN):
                self.state = GameState.PLAYING
            elif key == pygame.K_r:
                self.reset_game()
                self.state = GameState.PLAYING

        elif self.state == GameState.GAME_OVER:
            if key in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_r):
                self.reset_game()
                self.state = GameState.PLAYING
                self.sound_mgr.play("start")

    def update(self, dt):
        self.pulse_phase += dt * 4.0
        self.particles = [p for p in self.particles if p.update()]

        if self.golden_food:
            self.golden_timer -= 1
            if self.golden_timer <= 0:
                self.golden_food = None

        if self.state != GameState.PLAYING:
            self._update_stats_dict()
            return

        self.move_accumulator += dt
        move_interval = 1.0 / self.current_speed

        while self.move_accumulator >= move_interval:
            self.move_accumulator -= move_interval
            self.step_game()

        self._update_stats_dict()

    def step_game(self):
        # 1. Update Player 1 Direction
        if self.p1_queue:
            self.p1_dir = self.p1_queue.pop(0)
        h1 = self.p1_snake[0]
        new_h1 = (h1[0] + self.p1_dir[0], h1[1] + self.p1_dir[1])

        # 2. Update Player 2 / Bot Direction (if in versus mode)
        new_h2 = None
        if self.mode != GameMode.SOLO:
            if self.mode == GameMode.BOT:
                all_targets = list(self.foods)
                if self.golden_food:
                    all_targets.append(self.golden_food)
                self.p2_dir = get_bot_next_move(self.p2_snake[0], self.p2_snake, self.p1_snake, all_targets, self.p2_dir)
            elif self.p2_queue:
                self.p2_dir = self.p2_queue.pop(0)

            h2 = self.p2_snake[0]
            new_h2 = (h2[0] + self.p2_dir[0], h2[1] + self.p2_dir[1])

        # -----------------------------------------------------
        # COLLISION DETECTION & RESOLUTION
        # -----------------------------------------------------
        # Bounds check helper: Y must be >= PLAY_ROW_START (below HUD bar)
        def out_of_bounds(pos):
            return pos[0] < 0 or pos[0] >= GRID_COLS or pos[1] < PLAY_ROW_START or pos[1] >= GRID_ROWS

        p1_dead = False
        p2_dead = False
        p1_death_reason = ""
        p2_death_reason = ""

        # Player 1 Wall & Self Check
        if out_of_bounds(new_h1):
            p1_dead = True
            p1_death_reason = "Player 1 crashed into boundary wall!"
        elif new_h1 in self.p1_snake[:-1]:
            p1_dead = True
            p1_death_reason = "Player 1 collided with own body!"

        # Player 2 Wall & Self Check (Versus)
        if self.mode != GameMode.SOLO:
            p2_name = "CPU Bot" if self.mode == GameMode.BOT else "Player 2"
            if out_of_bounds(new_h2):
                p2_dead = True
                p2_death_reason = f"{p2_name} crashed into boundary wall!"
            elif new_h2 in self.p2_snake[:-1]:
                p2_dead = True
                p2_death_reason = f"{p2_name} collided with own body!"

            # Inter-Snake Collisions
            # Head-to-Head Collision
            if new_h1 == new_h2:
                if len(self.p1_snake) > len(self.p2_snake):
                    p2_dead = True
                    p2_death_reason = f"Head-on collision! Player 1 was longer than {p2_name}."
                elif len(self.p2_snake) > len(self.p1_snake):
                    p1_dead = True
                    p1_death_reason = f"Head-on collision! {p2_name} was longer than Player 1."
                else:
                    p1_dead = True
                    p2_dead = True
                    p1_death_reason = "Head-on collision with equal length!"

            # P1 hits P2 body
            elif new_h1 in self.p2_snake:
                p1_dead = True
                p1_death_reason = f"Player 1 crashed into {p2_name}'s snake!"

            # P2 hits P1 body
            elif new_h2 in self.p1_snake:
                p2_dead = True
                p2_death_reason = f"{p2_name} crashed into Player 1's snake!"

        # Check outcomes
        if p1_dead or p2_dead:
            self.resolve_round_over(p1_dead, p2_dead, p1_death_reason, p2_death_reason)
            return

        # -----------------------------------------------------
        # ADVANCE SNAKES & FOOD CONSUMPTION
        # -----------------------------------------------------
        # Player 1 advance
        self.p1_snake.insert(0, new_h1)
        p1_ate = False

        if self.golden_food and new_h1 == self.golden_food:
            self.p1_score += 30
            self.golden_food = None
            self.sound_mgr.play("golden")
            self.burst_particles(new_h1, COLOR_FOOD_GOLDEN)
            p1_ate = True
        elif new_h1 in self.foods:
            self.p1_score += 10
            self.p1_apples += 1
            self.foods.remove(new_h1)
            self.sound_mgr.play("eat")
            self.burst_particles(new_h1, COLOR_FOOD_APPLE)
            self.spawn_food()
            p1_ate = True

        if not p1_ate:
            self.p1_snake.pop()

        # Player 2 advance (Versus)
        if self.mode != GameMode.SOLO:
            self.p2_snake.insert(0, new_h2)
            p2_ate = False

            if self.golden_food and new_h2 == self.golden_food:
                self.p2_score += 30
                self.golden_food = None
                self.sound_mgr.play("golden")
                self.burst_particles(new_h2, COLOR_FOOD_GOLDEN)
                p2_ate = True
            elif new_h2 in self.foods:
                self.p2_score += 10
                self.p2_apples += 1
                self.foods.remove(new_h2)
                self.sound_mgr.play("eat")
                self.burst_particles(new_h2, COLOR_FOOD_APPLE)
                self.spawn_food()
                p2_ate = True

            if not p2_ate:
                self.p2_snake.pop()

        # Dynamic speed acceleration
        total_apples = self.p1_apples + self.p2_apples
        self.current_speed = min(22.0, self.base_speed + (total_apples * 0.35))

        if total_apples > 0 and total_apples % 5 == 0 and not self.golden_food:
            self.spawn_golden_food()

        # High score update for solo mode
        if self.mode == GameMode.SOLO and self.p1_score > self.high_score:
            self.high_score = self.p1_score
            self.is_new_high_score = True
            self.save_high_score()

    def burst_particles(self, pos, color):
        px = pos[0] * GRID_SIZE + GRID_SIZE // 2
        py = pos[1] * GRID_SIZE + GRID_SIZE // 2
        for _ in range(16):
            self.particles.append(Particle(px, py, color))

    def resolve_round_over(self, p1_dead, p2_dead, r1, r2):
        self.state = GameState.GAME_OVER
        self.sound_mgr.play("die")

        p2_name = "CPU Bot" if self.mode == GameMode.BOT else "Player 2"

        if self.mode == GameMode.SOLO:
            self.winner = None
            self.death_reason = r1
            self.save_high_score()
            self.burst_particles(self.p1_snake[0], COLOR_DANGER)
        else:
            if p1_dead and p2_dead:
                self.winner = "DRAW"
                self.death_reason = "Mutual Elimination!"
            elif p1_dead:
                self.winner = p2_name.upper()
                self.death_reason = r1
                self.p2_wins += 1
            else:
                self.winner = "PLAYER 1"
                self.death_reason = r2
                self.p1_wins += 1

            if p1_dead and self.p1_snake:
                self.burst_particles(self.p1_snake[0], COLOR_DANGER)
            if p2_dead and self.p2_snake:
                self.burst_particles(self.p2_snake[0], COLOR_DANGER)

    def _update_stats_dict(self):
        p2_label = "CPU" if self.mode == GameMode.BOT else "P2"
        self.stats = {
            "mode": self.mode,
            "state": self.state,
            "score": self.p1_score,
            "high_score": self.high_score,
            "length": len(self.p1_snake),
            "apples": self.p1_apples,
            "speed_level": round(self.current_speed, 1),
            "p1_score": self.p1_score,
            "p2_score": self.p2_score,
            "p1_wins": self.p1_wins,
            "p2_wins": self.p2_wins,
            "p2_label": p2_label,
            "reason": self.death_reason,
            "winner": self.winner,
        }

    # ---------------------------------------------------------
    # RENDERING ENGINE
    # ---------------------------------------------------------
    def render(self):
        self.screen.fill(COLOR_BG_DARK)
        self.draw_grid()

        for p in self.particles:
            p.draw(self.screen)

        self.draw_food()

        # Draw Snakes
        if self.mode != GameMode.SOLO:
            self.draw_snake(self.p2_snake, self.p2_dir, COLOR_P2_HEAD, COLOR_P2_BODY_1, COLOR_P2_BODY_2)
        self.draw_snake(self.p1_snake, self.p1_dir, COLOR_P1_HEAD, COLOR_P1_BODY_1, COLOR_P1_BODY_2)

        # Draw Clean Separated Top HUD Bar
        self.draw_hud()

        # Draw Overlays
        if self.state == GameState.START:
            self.draw_start_screen()
        elif self.state == GameState.PAUSED:
            self.draw_paused_screen()
        elif self.state == GameState.GAME_OVER:
            self.draw_game_over_screen()

        pygame.display.flip()

        if RUNNING_IN_BROWSER_MODE:
            self.capture_frame_jpeg()

    def capture_frame_jpeg(self):
        try:
            bio = io.BytesIO()
            pygame.image.save(self.screen, bio, "jpg")
            with self.frame_lock:
                self.latest_frame_bytes = bio.getvalue()
        except Exception:
            pass

    def _create_grid_surface(self):
        surf = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        surf.fill(COLOR_BG_DARK)

        # 1. Clear, alternating checkerboard tiles for instant cell visibility
        tile_a = (13, 18, 26)
        tile_b = (22, 30, 44)
        for gy in range(PLAY_ROW_START, GRID_ROWS):
            y = gy * GRID_SIZE
            for gx in range(GRID_COLS):
                x = gx * GRID_SIZE
                c = tile_a if (gx + gy) % 2 == 0 else tile_b
                pygame.draw.rect(surf, c, (x, y, GRID_SIZE, GRID_SIZE))

        # 2. Crisp, highly visible grid mesh lines
        grid_line_color = (48, 64, 90)
        for x in range(0, WINDOW_WIDTH + 1, GRID_SIZE):
            pygame.draw.line(surf, grid_line_color, (x, HUD_HEIGHT), (x, WINDOW_HEIGHT), 1)
        for y in range(HUD_HEIGHT, WINDOW_HEIGHT + 1, GRID_SIZE):
            pygame.draw.line(surf, grid_line_color, (0, y), (WINDOW_WIDTH, y), 1)

        # 3. Bold glowing perimeter border around the entire playable arena
        arena_rect = pygame.Rect(0, HUD_HEIGHT, WINDOW_WIDTH, WINDOW_HEIGHT - HUD_HEIGHT)
        pygame.draw.rect(surf, (0, 210, 255), arena_rect, 2)
        return surf

    def draw_grid(self):
        self.screen.blit(self.grid_surface, (0, 0))

    def draw_snake(self, snake_body, direction, head_color, body_c1, body_c2):
        if not snake_body:
            return

        snake_len = len(snake_body)
        for i, (gx, gy) in enumerate(snake_body):
            rect = pygame.Rect(gx * GRID_SIZE + 1, gy * GRID_SIZE + 1, GRID_SIZE - 2, GRID_SIZE - 2)
            if i == 0:
                pygame.draw.rect(self.screen, head_color, rect, border_radius=6)
                self.draw_snake_eyes(rect, direction)
            else:
                factor = min(1.0, i / max(1, snake_len))
                r = int(body_c1[0] * (1 - factor) + body_c2[0] * factor)
                g = int(body_c1[1] * (1 - factor) + body_c2[1] * factor)
                b = int(body_c1[2] * (1 - factor) + body_c2[2] * factor)
                radius = 4 if i < snake_len - 1 else 7
                pygame.draw.rect(self.screen, (r, g, b), rect, border_radius=radius)

    def draw_snake_eyes(self, head_rect, direction):
        dx, dy = direction
        cx = head_rect.centerx
        cy = head_rect.centery
        eye_offset = 4
        pupil_offset = 2

        if dx != 0:
            eye1 = (cx + dx * 3, cy - eye_offset)
            eye2 = (cx + dx * 3, cy + eye_offset)
            pupil1 = (eye1[0] + dx * pupil_offset, eye1[1])
            pupil2 = (eye2[0] + dx * pupil_offset, eye2[1])
        else:
            eye1 = (cx - eye_offset, cy + dy * 3)
            eye2 = (cx + eye_offset, cy + dy * 3)
            pupil1 = (eye1[0], eye1[1] + dy * pupil_offset)
            pupil2 = (eye2[0], eye2[1] + dy * pupil_offset)

        pygame.draw.circle(self.screen, COLOR_EYE_WHITE, eye1, 3)
        pygame.draw.circle(self.screen, COLOR_EYE_WHITE, eye2, 3)
        pygame.draw.circle(self.screen, COLOR_EYE_PUPIL, pupil1, 1)
        pygame.draw.circle(self.screen, COLOR_EYE_PUPIL, pupil2, 1)

    def draw_food(self):
        # Regular Apples (Pulsing Red)
        for apple in self.foods:
            gx, gy = apple
            cx = gx * GRID_SIZE + GRID_SIZE // 2
            cy = gy * GRID_SIZE + GRID_SIZE // 2

            pulse = math.sin(self.pulse_phase) * 1.5
            radius = max(3, int(GRID_SIZE // 2 - 2 + pulse))

            glow_surf = pygame.Surface((GRID_SIZE * 2, GRID_SIZE * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (255, 59, 48, 45), (GRID_SIZE, GRID_SIZE), radius + 4)
            self.screen.blit(glow_surf, (cx - GRID_SIZE, cy - GRID_SIZE))

            pygame.draw.circle(self.screen, COLOR_FOOD_APPLE, (cx, cy), radius)
            pygame.draw.circle(self.screen, (255, 180, 180), (cx - 2, cy - 2), max(1, radius // 3))
            pygame.draw.circle(self.screen, COLOR_FOOD_STEM, (cx + 3, cy - radius), 2)

        # Golden Apple (Sparkling Gold)
        if self.golden_food:
            gx, gy = self.golden_food
            cx = gx * GRID_SIZE + GRID_SIZE // 2
            cy = gy * GRID_SIZE + GRID_SIZE // 2

            pulse = math.sin(self.pulse_phase * 2) * 2.0
            radius = max(4, int(GRID_SIZE // 2 - 1 + pulse))

            glow_surf = pygame.Surface((GRID_SIZE * 2, GRID_SIZE * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (255, 215, 0, 70), (GRID_SIZE, GRID_SIZE), radius + 6)
            self.screen.blit(glow_surf, (cx - GRID_SIZE, cy - GRID_SIZE))

            pygame.draw.circle(self.screen, COLOR_FOOD_GOLDEN, (cx, cy), radius)
            pygame.draw.circle(self.screen, (255, 255, 230), (cx - 2, cy - 2), max(1, radius // 3))

    def draw_hud(self):
        """Draws the top HUD bar and a crisp boundary line separating it from the game grid."""
        hud_surface = pygame.Surface((WINDOW_WIDTH, HUD_HEIGHT), pygame.SRCALPHA)
        hud_surface.fill((13, 17, 23, 230))
        self.screen.blit(hud_surface, (0, 0))

        # Glowing boundary separator at y = HUD_HEIGHT (40px)
        pygame.draw.line(self.screen, (0, 176, 255), (0, HUD_HEIGHT), (WINDOW_WIDTH, HUD_HEIGHT), 2)

        if self.mode == GameMode.SOLO:
            score_txt = self.font_medium.render(f"SCORE: {self.p1_score}", True, COLOR_TEXT_PRIMARY)
            self.screen.blit(score_txt, (20, 8))

            best_label = "BESTE" if self.language == "de" else "BEST"
            hi_txt = self.font_small.render(f"{best_label}: {self.high_score}", True, COLOR_TEXT_ACCENT)
            self.screen.blit(hi_txt, (WINDOW_WIDTH - hi_txt.get_width() - 20, 11))

            mid_str = f"LENGTH: {len(self.p1_snake)}   |   SPEED: {round(self.current_speed, 1)}x"
            mid_txt = self.font_small.render(mid_str, True, COLOR_TEXT_MUTED)
            self.screen.blit(mid_txt, ((WINDOW_WIDTH - mid_txt.get_width()) // 2, 11))

        else:
            # Versus HUD: Player 1 (Cyan) vs Player 2 / Bot (Magenta)
            p2_label = "CPU BOT" if self.mode == GameMode.BOT else "PLAYER 2"

            p1_str = f"P1: {self.p1_score} (WINS: {self.p1_wins})"
            p1_txt = self.font_medium.render(p1_str, True, COLOR_P1_HEAD)
            self.screen.blit(p1_txt, (20, 8))

            p2_str = f"{p2_label}: {self.p2_score} (WINS: {self.p2_wins})"
            p2_txt = self.font_medium.render(p2_str, True, COLOR_P2_HEAD)
            self.screen.blit(p2_txt, (WINDOW_WIDTH - p2_txt.get_width() - 20, 8))

            mode_name = "2P VERSUS" if self.mode == GameMode.PVP else "VS CPU"
            mid_txt = self.font_small.render(mode_name, True, COLOR_TEXT_ACCENT)
            self.screen.blit(mid_txt, ((WINDOW_WIDTH - mid_txt.get_width()) // 2, 11))

    def draw_start_screen(self):
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((13, 17, 23, 215))
        self.screen.blit(overlay, (0, 0))

        title_txt = self.font_large.render("NEON SNAKE", True, COLOR_P1_HEAD)
        self.screen.blit(title_txt, ((WINDOW_WIDTH - title_txt.get_width()) // 2, 120))

        mode_desc = {
            GameMode.SOLO: "Solo Mode - Classic High Score Chase",
            GameMode.PVP: "2-Player Versus - P1 (Arrows) vs P2 (WASD)",
            GameMode.BOT: "Versus CPU - Challenge the Intelligent AI Bot",
        }[self.mode]
        sub_txt = self.font_small.render(mode_desc, True, COLOR_TEXT_ACCENT)
        self.screen.blit(sub_txt, ((WINDOW_WIDTH - sub_txt.get_width()) // 2, 180))

        # Mode Selection & Controls Card
        panel_rect = pygame.Rect((WINDOW_WIDTH - 460) // 2, 220, 460, 210)
        pygame.draw.rect(self.screen, (22, 27, 34), panel_rect, border_radius=12)
        pygame.draw.rect(self.screen, (48, 54, 61), panel_rect, 1, border_radius=12)

        lines = [
            ("SELECT GAME MODE [ 1, 2, 3 or M ]", COLOR_TEXT_PRIMARY, self.font_small),
            (f"[ 1 ] Solo Play {'(ACTIVE)' if self.mode == GameMode.SOLO else ''}", COLOR_P1_HEAD if self.mode == GameMode.SOLO else COLOR_TEXT_MUTED, self.font_small),
            (f"[ 2 ] 2-Player Local PvP {'(ACTIVE)' if self.mode == GameMode.PVP else ''}", COLOR_P2_HEAD if self.mode == GameMode.PVP else COLOR_TEXT_MUTED, self.font_small),
            (f"[ 3 ] Versus CPU AI Bot {'(ACTIVE)' if self.mode == GameMode.BOT else ''}", COLOR_TEXT_ACCENT if self.mode == GameMode.BOT else COLOR_TEXT_MUTED, self.font_small),
            ("CONTROLS: P1 (Arrows/WASD) | P2 (WASD)", COLOR_TEXT_PRIMARY, self.font_small),
            ("Apples never spawn under top HUD boundary", COLOR_P1_BODY_1, self.font_small),
        ]
        curr_y = panel_rect.y + 16
        for text, color, font in lines:
            rendered = font.render(text, True, color)
            self.screen.blit(rendered, ((WINDOW_WIDTH - rendered.get_width()) // 2, curr_y))
            curr_y += 30

        pulse_val = (math.sin(self.pulse_phase * 1.5) + 1.0) / 2.0
        prompt_color = (
            int(COLOR_P1_HEAD[0] * 0.4 + COLOR_P1_HEAD[0] * 0.6 * pulse_val),
            int(COLOR_P1_HEAD[1] * 0.4 + COLOR_P1_HEAD[1] * 0.6 * pulse_val),
            int(COLOR_P1_HEAD[2] * 0.4 + COLOR_P1_HEAD[2] * 0.6 * pulse_val),
        )
        prompt_txt = self.font_medium.render("Press  [ SPACE ]  or  [ ENTER ]  to Play", True, prompt_color)
        self.screen.blit(prompt_txt, ((WINDOW_WIDTH - prompt_txt.get_width()) // 2, 470))

    def draw_paused_screen(self):
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((13, 17, 23, 190))
        self.screen.blit(overlay, (0, 0))

        paused_txt = self.font_large.render("PAUSED", True, COLOR_TEXT_ACCENT)
        self.screen.blit(paused_txt, ((WINDOW_WIDTH - paused_txt.get_width()) // 2, 230))

        sub_txt = self.font_medium.render("Press  [ P ]  or  [ SPACE ]  to Resume", True, COLOR_TEXT_PRIMARY)
        self.screen.blit(sub_txt, ((WINDOW_WIDTH - sub_txt.get_width()) // 2, 305))

        m_txt = self.font_small.render("Press  [ M ]  to switch game mode", True, COLOR_TEXT_MUTED)
        self.screen.blit(m_txt, ((WINDOW_WIDTH - m_txt.get_width()) // 2, 360))

    def draw_game_over_screen(self):
        overlay = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        overlay.fill((13, 17, 23, 215))
        self.screen.blit(overlay, (0, 0))

        if self.mode == GameMode.SOLO:
            go_txt = self.font_large.render("GAME OVER", True, COLOR_DANGER)
            self.screen.blit(go_txt, ((WINDOW_WIDTH - go_txt.get_width()) // 2, 120))

            reason_txt = self.font_small.render(self.death_reason, True, COLOR_TEXT_MUTED)
            self.screen.blit(reason_txt, ((WINDOW_WIDTH - reason_txt.get_width()) // 2, 185))

            panel_rect = pygame.Rect((WINDOW_WIDTH - 380) // 2, 220, 380, 160)
            pygame.draw.rect(self.screen, (22, 27, 34), panel_rect, border_radius=12)
            pygame.draw.rect(self.screen, (48, 54, 61), panel_rect, 1, border_radius=12)

            s_txt = self.font_medium.render(f"Final Score:  {self.p1_score}", True, COLOR_TEXT_PRIMARY)
            self.screen.blit(s_txt, ((WINDOW_WIDTH - s_txt.get_width()) // 2, panel_rect.y + 24))

            best_color = COLOR_TEXT_ACCENT if not self.is_new_high_score else (0, 255, 128)
            if self.language == "de":
                best_label = "NEUER HIGHSCORE!" if self.is_new_high_score else f"Persönlicher Bestwert:  {self.high_score}"
            else:
                best_label = "NEW HIGH SCORE!" if self.is_new_high_score else f"Personal Best:  {self.high_score}"
            h_txt = self.font_medium.render(best_label, True, best_color)
            self.screen.blit(h_txt, ((WINDOW_WIDTH - h_txt.get_width()) // 2, panel_rect.y + 65))

            len_txt = self.font_small.render(f"Apples: {self.p1_apples}   |   Length: {len(self.p1_snake)}", True, COLOR_TEXT_MUTED)
            self.screen.blit(len_txt, ((WINDOW_WIDTH - len_txt.get_width()) // 2, panel_rect.y + 115))

        else:
            # Versus Outcome
            win_color = COLOR_P1_HEAD if self.winner == "PLAYER 1" else (COLOR_P2_HEAD if self.winner != "DRAW" else COLOR_TEXT_ACCENT)
            win_banner = f"{self.winner} WINS!" if self.winner != "DRAW" else "ROUND DRAW!"
            win_txt = self.font_large.render(win_banner, True, win_color)
            self.screen.blit(win_txt, ((WINDOW_WIDTH - win_txt.get_width()) // 2, 120))

            reason_txt = self.font_small.render(self.death_reason, True, COLOR_TEXT_MUTED)
            self.screen.blit(reason_txt, ((WINDOW_WIDTH - reason_txt.get_width()) // 2, 185))

            panel_rect = pygame.Rect((WINDOW_WIDTH - 420) // 2, 220, 420, 160)
            pygame.draw.rect(self.screen, (22, 27, 34), panel_rect, border_radius=12)
            pygame.draw.rect(self.screen, (48, 54, 61), panel_rect, 1, border_radius=12)

            p2_label = "CPU Bot" if self.mode == GameMode.BOT else "Player 2"
            score_line = f"P1: {self.p1_score} pts  vs  {p2_label}: {self.p2_score} pts"
            sc_txt = self.font_medium.render(score_line, True, COLOR_TEXT_PRIMARY)
            self.screen.blit(sc_txt, ((WINDOW_WIDTH - sc_txt.get_width()) // 2, panel_rect.y + 24))

            series_line = f"Series Standing:  P1 ({self.p1_wins})  -  {p2_label} ({self.p2_wins})"
            se_txt = self.font_medium.render(series_line, True, COLOR_TEXT_ACCENT)
            self.screen.blit(se_txt, ((WINDOW_WIDTH - se_txt.get_width()) // 2, panel_rect.y + 65))

            len_line = f"Lengths: P1 ({len(self.p1_snake)})  |  {p2_label} ({len(self.p2_snake)})"
            le_txt = self.font_small.render(len_line, True, COLOR_TEXT_MUTED)
            self.screen.blit(le_txt, ((WINDOW_WIDTH - le_txt.get_width()) // 2, panel_rect.y + 115))

        pulse_val = (math.sin(self.pulse_phase * 2.0) + 1.0) / 2.0
        r_color = (
            int(COLOR_P1_HEAD[0] * 0.5 + COLOR_P1_HEAD[0] * 0.5 * pulse_val),
            int(COLOR_P1_HEAD[1] * 0.5 + COLOR_P1_HEAD[1] * 0.5 * pulse_val),
            int(COLOR_P1_HEAD[2] * 0.5 + COLOR_P1_HEAD[2] * 0.5 * pulse_val),
        )
        restart_txt = self.font_medium.render("Press  [ SPACE ]  or  [ ENTER ]  for Next Round", True, r_color)
        self.screen.blit(restart_txt, ((WINDOW_WIDTH - restart_txt.get_width()) // 2, 420))

        m_hint = self.font_small.render("Press  [ M ]  or  [ 1, 2, 3 ]  to Change Game Mode", True, COLOR_TEXT_MUTED)
        self.screen.blit(m_hint, ((WINDOW_WIDTH - m_hint.get_width()) // 2, 465))


# ---------------------------------------------------------
# HYBRID ZERO-DEPENDENCY HTTP & WEBSOCKET SERVER
# ---------------------------------------------------------
def encode_ws_frame(data, opcode=0x02):
    length = len(data)
    if length <= 125:
        header = bytes([0x80 | opcode, length])
    elif length <= 65535:
        header = struct.pack("!BBH", 0x80 | opcode, 126, length)
    else:
        header = struct.pack("!BBQ", 0x80 | opcode, 127, length)
    return header + data


def ensure_offline_zip():
    dl_dir = "dl"
    os.makedirs(dl_dir, exist_ok=True)
    zip_path = os.path.join(dl_dir, "neon-snake-offline.zip")
    files_to_pack = ["main.py", "index.html", "style.css", "client.js", "highscore.json", "start.bat", "README.md"]
    try:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for f in files_to_pack:
                if os.path.exists(f):
                    zipf.write(f, arcname=f)
    except Exception:
        pass


class SnakeServerHandler(http.server.BaseHTTPRequestHandler):
    game_instance = None

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.headers.get("Upgrade", "").lower() == "websocket":
            self.handle_websocket()
            return

        parsed = urllib.parse.urlparse(self.path)
        url_path = parsed.path

        if url_path in ("/", "/index.html"):
            if os.path.exists("index.html"):
                with open("index.html", "rb") as f:
                    content = f.read()
            else:
                content = b"<h1>Neon Snake</h1>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif url_path == "/style.css":
            if os.path.exists("style.css"):
                with open("style.css", "rb") as f:
                    content = f.read()
            else:
                content = b""
            self.send_response(200)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif url_path == "/client.js":
            if os.path.exists("client.js"):
                with open("client.js", "rb") as f:
                    content = f.read()
            else:
                content = b""
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        elif url_path == "/state":
            stats = self.game_instance.stats if self.game_instance else {}
            body = json.dumps(stats).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif url_path.startswith("/dl/") or url_path == "/dl":
            ensure_offline_zip()
            rel_path = url_path.lstrip("/")
            safe_path = os.path.normpath(rel_path)
            if not safe_path.startswith("dl") or ".." in safe_path:
                self.send_error(403, "Forbidden")
                return

            if os.path.isdir(safe_path) or safe_path == "dl":
                safe_path = os.path.join("dl", "neon-snake-offline.zip")

            if os.path.exists(safe_path) and os.path.isfile(safe_path):
                filename = os.path.basename(safe_path)
                with open(safe_path, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/zip")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            else:
                self.send_error(404, "File Not Found")

        elif url_path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-cache, private, no-store, must-revalidate")
            self.end_headers()

            try:
                last_sent = None
                while True:
                    frame = None
                    if self.game_instance:
                        with self.game_instance.frame_lock:
                            frame = self.game_instance.latest_frame_bytes

                    if frame and frame != last_sent:
                        last_sent = frame
                        header = (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            b"Content-Length: " + str(len(frame)).encode("ascii") + b"\r\n\r\n"
                        )
                        self.wfile.write(header + frame + b"\r\n")
                        self.wfile.flush()
                    time.sleep(0.016)
            except (ConnectionResetError, BrokenPipeError):
                pass
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        url_path = urllib.parse.urlparse(self.path).path
        if url_path == "/input":
            length = int(self.headers.get("Content-Length", 0))
            key_data = self.rfile.read(length).decode("utf-8").strip()
            if self.game_instance and key_data:
                self.game_instance.queue_key_event(key_data)

            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"OK")
        elif url_path == "/mode":
            length = int(self.headers.get("Content-Length", 0))
            mode_req = self.rfile.read(length).decode("utf-8").strip().upper()
            if self.game_instance:
                if mode_req in (GameMode.SOLO, GameMode.PVP, GameMode.BOT):
                    self.game_instance.cycle_mode(mode_req)
                else:
                    self.game_instance.cycle_mode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_error(404)

    def handle_websocket(self):
        key = self.headers.get("Sec-WebSocket-Key", "")
        guid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
        accept = base64.b64encode(hashlib.sha1((key + guid).encode("utf-8")).digest()).decode("utf-8")

        try:
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass

        handshake_resp = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        )
        self.wfile.write(handshake_resp.encode("ascii"))
        self.wfile.flush()

        sock = self.connection
        active = [True]

        def reader():
            buf = bytearray()
            while active[0]:
                try:
                    chunk = sock.recv(2048)
                    if not chunk:
                        break
                    buf.extend(chunk)

                    while len(buf) >= 2:
                        b1, b2 = buf[0], buf[1]
                        opcode = b1 & 0x0F
                        masked = (b2 & 0x80) != 0
                        length = b2 & 0x7F
                        offset = 2

                        if length == 126:
                            if len(buf) < 4:
                                break
                            length = struct.unpack("!H", buf[2:4])[0]
                            offset = 4
                        elif length == 127:
                            if len(buf) < 10:
                                break
                            length = struct.unpack("!Q", buf[2:10])[0]
                            offset = 10

                        if masked:
                            if len(buf) < offset + 4 + length:
                                break
                            mask_key = buf[offset:offset + 4]
                            raw_data = buf[offset + 4:offset + 4 + length]
                            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(raw_data))
                            del buf[:offset + 4 + length]
                        else:
                            if len(buf) < offset + length:
                                break
                            payload = bytes(buf[offset:offset + length])
                            del buf[:offset + length]

                        if opcode == 0x08:
                            active[0] = False
                            return
                        elif opcode == 0x09:
                            sock.sendall(bytes([0x8A, 0]))
                        elif opcode == 0x01:
                            msg = payload.decode("utf-8", errors="ignore").strip()
                            if self.game_instance and msg:
                                if msg.startswith("MODE:"):
                                    req_mode = msg.split(":", 1)[1]
                                    self.game_instance.cycle_mode(req_mode if req_mode in (GameMode.SOLO, GameMode.PVP, GameMode.BOT) else None)
                                elif msg.startswith("HIGH_SCORE:"):
                                    self.game_instance.set_browser_high_score(msg.split(":", 1)[1])
                                elif msg.startswith("LANG:"):
                                    self.game_instance.set_language(msg.split(":", 1)[1])
                                else:
                                    self.game_instance.queue_key_event(msg)
                except Exception:
                    break
            active[0] = False

        r_thread = threading.Thread(target=reader, daemon=True)
        r_thread.start()

        try:
            last_frame = None
            while active[0]:
                frame = None
                if self.game_instance:
                    with self.game_instance.frame_lock:
                        frame = self.game_instance.latest_frame_bytes

                if frame and frame != last_frame:
                    last_frame = frame
                    sock.sendall(encode_ws_frame(frame, opcode=0x02))

                time.sleep(0.016)
        except Exception:
            pass
        finally:
            active[0] = False


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


def start_local_web_server(game, port=8000):
    SnakeServerHandler.game_instance = game
    server = None
    for p in range(port, port + 20):
        try:
            server = ThreadedTCPServer(("127.0.0.1", p), SnakeServerHandler)
            port = p
            break
        except OSError:
            continue

    if not server:
        print("Could not bind to an available port for local server.")
        return None, None

    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, port


# ---------------------------------------------------------
# MAIN ASYNC LOOP (Compatible with pygbag, native & browser)
# ---------------------------------------------------------
async def main():
    parser = argparse.ArgumentParser(description="Neon Snake - Pygame Community Edition")
    parser.add_argument("--desktop", "--window", action="store_true", help="Launch native desktop Pygame window")
    parser.add_argument("--port", type=int, default=8000, help="Local web server port [default: 8000]")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically launch web browser")
    args, _ = parser.parse_known_args()

    game = SnakeGame()

    if sys.platform != "emscripten" and not args.desktop:
        server, port = start_local_web_server(game, port=args.port)
        if server:
            local_url = f"http://localhost:{port}"
            print("=" * 64)
            print("NEON SNAKE - PYGAME COMMUNITY EDITION")
            print("=" * 64)
            print(f"Game is running locally at: {local_url}")
            print("Solo Mode: ARROW KEYS or WASD to move")
            print("Versus Mode: P1 = Arrow Keys | P2 = W, A, S, D")
            print("Press 1, 2, 3 or M to switch game mode")
            print("=" * 64)

            if not args.no_browser:
                def open_browser():
                    time.sleep(0.5)
                    webbrowser.open(local_url)
                threading.Thread(target=open_browser, daemon=True).start()

    last_time = time.perf_counter()
    running = True

    while running:
        current_time = time.perf_counter()
        dt = current_time - last_time
        last_time = current_time
        dt = min(dt, 0.1)

        game.handle_input()
        game.update(dt)
        game.render()

        game.clock.tick(60)
        await asyncio.sleep(0)

    pygame.quit()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nSnake game terminated gracefully.")
        sys.exit(0)
