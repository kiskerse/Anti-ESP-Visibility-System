from __future__ import annotations

import math
import time
import tkinter as tk
from typing import Any

from security.state import StateMemory


class Client:
    """Client view: renders what the server wrote into StateMemory.

    The server is authoritative for visibility and updates `memory`.
    Dead-reckoning (DR) from StateMemory is used to smooth movement between
    ticks and eliminate teleport pop-in without revealing extra information.
    """

    def __init__(
        self,
        client_id: str,
        shared_state: dict[str, Any],
        memory: StateMemory,
        fov_deg: float = 90.0,
        radius: float = 10.0,
        dir_angle: float = 0.0,
        cell_size: int = 50,
        window_size: tuple[int, int] = (600, 600),
        fps: int | None = 120,
    ) -> None:
        self.client_id = client_id
        self.shared_state = shared_state
        self.memory = memory
        self.fov = math.radians(fov_deg)
        self.radius = radius
        self.dir_angle = dir_angle
        self.cell_size = cell_size
        self.requested_fps = fps

        # lerp display positions (for full-visibility players)
        self.display_positions: dict[str, tuple[float, float]] = {}
        self.lerp_factor = 0.25

        # stable partial-zone areas (avoid jitter)
        self.partial_stable: dict[str, tuple[int, int]] = {}
        self.partial_stable_ts: dict[str, float] = {}

        # label to distinguish DR-predicted draws
        self._dr_active: set[str] = set()

        self.root = tk.Toplevel()
        self.root.title(f"Client View — {client_id}")

        map_w = self.shared_state.get("map_width") or (window_size[0] // self.cell_size)
        map_h = self.shared_state.get("map_height") or (window_size[1] // self.cell_size)
        w = map_w * self.cell_size
        h = map_h * self.cell_size
        self.canvas = tk.Canvas(self.root, width=w, height=h, bg="black")
        self.canvas.pack()

        # legend
        self._draw_legend()

        self._running = True
        interval = int(max(1, 1000 / (fps if fps and fps > 0 else 120)))
        self._interval_ms = interval
        self.update_loop()

    # ------------------------------------------------------------------
    # Render helpers
    # ------------------------------------------------------------------

    def _draw_legend(self) -> None:
        """Overlay a small fixed legend on the canvas."""
        pass  # drawn dynamically each frame in draw()

    def draw(self) -> None:
        """Render based only on StateMemory (no visibility computation here)."""
        self.canvas.delete("all")
        positions = self.shared_state.get("positions", {})
        now = time.time()

        # draw obstacles
        for obs in self.shared_state.get("obstacles", []):
            ox, oy, ow, oh, cor, estilo = obs
            x1 = ox * self.cell_size
            y1 = oy * self.cell_size
            x2 = (ox + ow) * self.cell_size
            y2 = (oy + oh) * self.cell_size
            fill = cor if estilo == "solid" else ""
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=cor)

        self._dr_active.clear()

        for pid, pos in positions.items():
            x, y, _ = pos
            px = x * self.cell_size + self.cell_size / 2
            py = y * self.cell_size + self.cell_size / 2
            r = max(4, self.cell_size // 4)
            mem = self.memory.get_state(pid) or {}
            level = mem.get("level", "none")

            # ---- self ----
            if pid == self.client_id:
                self.canvas.create_oval(px - r, py - r, px + r, py + r, fill="cyan")
                self.display_positions[pid] = (px, py)
                continue

            # ---- not visible ----
            if level == "none":
                # try dead-reckoning for a brief grace period (100 ms)
                dr_pos = self.memory.get_predicted_pos(pid, self.cell_size)
                if dr_pos is not None:
                    # only use DR if the player was recently seen (tracked in _dr)
                    # show faded ghost to avoid teleport pop-out
                    dpx, dpy = dr_pos
                    color = "#660000" if str(pid).startswith("enemy") else "#006600"
                    self.canvas.create_oval(
                        dpx - r, dpy - r, dpx + r, dpy + r,
                        fill=color, outline="#888888", dash=(2, 4),
                    )
                    self._dr_active.add(str(pid))
                else:
                    self.display_positions.pop(pid, None)
                continue

            # ---- full visibility ----
            if level == "full":
                # prefer dead-reckoning predicted position to smooth between ticks
                dr_pos = self.memory.get_predicted_pos(pid, self.cell_size)
                if dr_pos is not None:
                    target = dr_pos
                else:
                    target = (px, py)

                cur = self.display_positions.get(pid, target)
                nx = cur[0] + (target[0] - cur[0]) * self.lerp_factor
                ny = cur[1] + (target[1] - cur[1]) * self.lerp_factor
                self.display_positions[pid] = (nx, ny)

                color = "red" if str(pid).startswith("enemy") else "green"
                self.canvas.create_oval(nx - r, ny - r, nx + r, ny + r, fill=color)
                continue

            # ---- partial / position_only: probable area zone ----
            reported = mem.get("pos")
            if reported is None:
                continue
            rx, ry = int(reported[0]), int(reported[1])

            # stabilise reported position for short window to avoid jitter
            stable = self.partial_stable.get(pid)
            last_ts = self.partial_stable_ts.get(pid, 0.0)
            if stable is None or stable != (rx, ry) or (now - last_ts) > 0.2:
                self.partial_stable[pid] = (rx, ry)
                self.partial_stable_ts[pid] = now
            rx_st, ry_st = self.partial_stable[pid]

            area_cells = 3 if level == "partial" else 5
            ax = rx_st * self.cell_size + self.cell_size / 2
            ay = ry_st * self.cell_size + self.cell_size / 2
            half = (area_cells * self.cell_size) / 2
            outline = "#ff8080" if str(pid).startswith("enemy") else "#80ff80"
            fill_c = "#ffb3b3" if str(pid).startswith("enemy") else "#b3ffb3"
            self.canvas.create_oval(ax - half, ay - half, ax + half, ay + half,
                                    outline=outline, fill=fill_c)

        # draw client FOV cone (visual reference only)
        cp = positions.get(self.client_id)
        if cp:
            cx, cy, _ = cp
            ox = cx * self.cell_size + self.cell_size / 2
            oy = cy * self.cell_size + self.cell_size / 2
            la = self.dir_angle - self.fov / 2
            ra = self.dir_angle + self.fov / 2
            fov_r = self.radius * self.cell_size
            self.canvas.create_line(ox, oy, ox + math.cos(la) * fov_r, oy + math.sin(la) * fov_r, fill="white")
            self.canvas.create_line(ox, oy, ox + math.cos(ra) * fov_r, oy + math.sin(ra) * fov_r, fill="white")

        # legend
        self._draw_legend_overlay()

    def _draw_legend_overlay(self) -> None:
        items = [
            ("■ You",           "cyan"),
            ("■ Enemy (full)",  "red"),
            ("■ Ally (full)",   "green"),
            ("○ Probable area (partial)", "#ff8080"),
            ("○ Wider area (position_only)", "#ffb3b3"),
            ("⋯ DR ghost (leaving FOV)", "#660000"),
        ]
        y0 = 6
        for label, color in items:
            self.canvas.create_text(8, y0, text=label, fill=color, anchor="nw", font=("Courier", 8))
            y0 += 12

    def update_loop(self) -> None:
        if not self._running:
            return
        try:
            self.draw()
        except Exception:
            pass
        self.root.after(self._interval_ms, self.update_loop)

    def stop(self) -> None:
        self._running = False
        try:
            self.root.destroy()
        except Exception:
            pass
