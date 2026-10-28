# Neon Snake - Standalone Web Edition

A complete Snake game built with HTML, CSS, JavaScript, and Canvas. It runs entirely in the browser with no Python server, backend, WebSocket, or external dependencies.

---

## Game Modes

1. **Solo Mode**: Classic single-player high-score challenge.
2. **2-Player Versus (Local PvP)**: Two players on the same screen! Player 1 (Cyan) uses Arrow Keys, Player 2 (Magenta) uses WASD.
3. **Versus CPU Bot**: Play against a smart AI bot with obstacle avoidance and dynamic pathfinding!

---

## Controls

| Mode | Player 1 (Cyan) | Player 2 (Magenta / Bot) |
| :--- | :--- | :--- |
| **Solo Mode** | Arrow Keys or W / A / S / D | N/A |
| **2-Player Versus** | Arrow Keys (Up, Down, Left, Right) | W, A, S, D |
| **Versus CPU** | Arrow Keys or W / A / S / D | Controlled by AI Bot |

### General Controls
- **1, 2, 3 or M**: Switch Game Mode (Solo / 2P Versus / Vs CPU)
- **SPACE or ENTER**: Start / Play Next Round
- **P or ESC**: Pause / Resume
- **R**: Quick Restart

---

## How to Run

### On GitHub Pages

Open the repository's **Settings → Pages**, choose **Deploy from a branch**, select the `main` branch and `/ (root)`, then save. GitHub Pages serves `index.html` directly.

For local testing, open `index.html` in a browser or run:

```bash
python -m http.server 8000
```

Then open `http://localhost:8000`.

---

## Features

- **No HUD Food Shadowing Bug**: The playable grid is strictly separated from the top HUD bar (boundary line at y = 40px). Apples can never spawn under or be shadowed by the HUD.
- **Standalone Client**: The complete game loop runs locally in Canvas with no backend.
- **Auto-Fitting Viewport**: Responsive canvas layout that dynamically scales to any screen size without vertical or horizontal scrolling.
- **Multi-Apple Spawning**: Multiple apples active in versus mode for fast-paced competitive action.
- **Inter-Snake Collision Resolution**: Tail hits, wall hits, and head-on collisions (longer snake wins).
- **Procedural Audio**: Real-time sound effects generated without external audio assets.
- **Offline Download Package**: A "Download Offline" button in the web interface provides a direct download link to `dl/neon-snake-offline.zip`, containing all standalone files.
- **Zero Emojis**: Clean, professional retro arcade aesthetics.
- **Browser Personal Best**: Scores persist with `localStorage`.
- **English / German**: Switch languages with the top-right language button.
