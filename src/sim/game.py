from __future__ import annotations
import math
import tkinter as tk
from typing import Any, List
import random

# state.positions é uma matriz 3x1 indicando a posição

class Game:
    def __init__(
        self,
        istate: dict[str, Any],
        config: dict[str, Any],
        create_ui: bool = True,
    ) -> None:
        self.istate = istate
        self.largura = config.get("largura", 10_000)
        self.altura = config.get("altura", 10_000)
        self.tamanho_celula = config.get("tamanho_celula", 100)
        self.cor = config.get("cor", "black")
        self.ui = create_ui
        self.root = None
        if self.ui:
            self.root = tk.Toplevel()
        # obstaculos are stored in grid cell coordinates: (x, y, largura, altura, cor, estilo)
        self.obstaculos: List[tuple[int, int, int, int, str, str]] = config.get(
            "obstaculos", []
        )
        self.canvas = None
        if self.ui and self.root is not None:
            self.canvas = tk.Canvas(self.root, width=self.largura, height=self.altura, bg=self.cor)
            self.canvas.pack()
        # store lines_of_sight per player id: pid -> list[ (ox,oy,hitx,hity) ]
        self.lines_of_sight_by_player: dict[str, list[tuple[int, int, int, int]]] = {}
        # caching helpers: avoid recomputing rays when players/obstacles didn't move
        self.last_positions: dict[str, tuple[int, int]] = {}
        self.obstacles_version = 0
        self.last_obstacles_version = 0
        # raycasting tuning
        self.n_rays = config.get("n_rays", 180)

    def draw_players(self, state: dict[str, Any]) -> None:
        # draw a simple map representing the player positions
        for pid, position in state["positions"].items():
            x, y, _ = position
            canvas_x = x * self.tamanho_celula + self.tamanho_celula / 2
            canvas_y = y * self.tamanho_celula + self.tamanho_celula / 2
            # smaller avatar so it fits inside a cell
            r = max(4, self.tamanho_celula // 4)
            # color enemies red (ids starting with 'enemy'), client/players blue
            color = "red" if str(pid).startswith("enemy") else "blue"
            if self.canvas:
                self.canvas.create_oval(
                    canvas_x - r,
                    canvas_y - r,
                    canvas_x + r,
                    canvas_y + r,
                    fill=color,
                )

            # recompute rays only when player moved or obstacles changed
            last = self.last_positions.get(str(pid))
            if last != (int(x), int(y)) or self.last_obstacles_version != self.obstacles_version:
                self.compute_lines_of_sight(pid, position)
            # draw cached rays (fast)
            if self.canvas:
                self.draw_rays(pid)

    def generate_obstacle(self) -> tuple[int, int, int, int, str, str]:
        x = random.randint(0, self.largura // self.tamanho_celula - 1)
        y = random.randint(0, self.altura // self.tamanho_celula - 1)

        largura = random.randint(
            max(1, self.largura // self.tamanho_celula // 10),
            max(1, self.largura // self.tamanho_celula // 5),
        )
        altura = random.randint(
            max(1, self.altura // self.tamanho_celula // 10),
            max(1, self.altura // self.tamanho_celula // 5),
        )

        cor = "grey"
        estilo = "solid"

        return (x, y, largura, altura, cor, estilo)


    def draw_random_obstacles(self) -> None:
        # generate obstacles only once; subsequent calls redraw existing ones
        if not self.obstaculos:
            count = random.randint(5, 15)
            for _ in range(count):
                obs = self.generate_obstacle()
                self.obstaculos.append(obs)
            # bump version when obstacles created
            self.obstacles_version += 1

        for obs in self.obstaculos:
            x, y, largura, altura, cor, estilo = obs
            canvas_x1 = x * self.tamanho_celula
            canvas_y1 = y * self.tamanho_celula
            canvas_x2 = (x + largura) * self.tamanho_celula
            canvas_y2 = (y + altura) * self.tamanho_celula
            fill = cor if estilo == "solid" else ""
            if self.canvas:
                self.canvas.create_rectangle(
                    canvas_x1, canvas_y1, canvas_x2, canvas_y2, fill=fill, outline=cor
                )

    def _point_hits_obstacle(self, px: float, py: float) -> bool:
        # check whether the point (pixels) is inside any obstacle (grid coords)
        gx = px / self.tamanho_celula
        gy = py / self.tamanho_celula
        for obs in self.obstaculos:
            ox, oy, ow, oh, _, _ = obs
            if ox <= gx <= ox + ow and oy <= gy <= oy + oh:
                return True
        return False
    def compute_lines_of_sight(self, pid: str, pos: tuple[int, int, int]) -> None:
        """Compute rays for pid and store them (no drawing)."""
        n_rays = self.n_rays
        max_distance = max(self.largura, self.altura)
        step = max(4, self.tamanho_celula // 6)

        x, y, _ = pos
        origin_x = x * self.tamanho_celula + self.tamanho_celula / 2
        origin_y = y * self.tamanho_celula + self.tamanho_celula / 2

        rays: list[tuple[int, int, int, int]] = []
        for i in range(n_rays):
            angle = (2 * math.pi * i) / n_rays
            dx = math.cos(angle)
            dy = math.sin(angle)

            hit_x = origin_x + max_distance * dx
            hit_y = origin_y + max_distance * dy
            dist = 0.0
            while dist <= max_distance:
                sx = origin_x + dx * dist
                sy = origin_y + dy * dist
                if sx < 0 or sx > self.largura or sy < 0 or sy > self.altura:
                    hit_x, hit_y = sx, sy
                    break
                if self._point_hits_obstacle(sx, sy):
                    hit_x, hit_y = sx, sy
                    break
                dist += step

            rays.append((int(origin_x), int(origin_y), int(hit_x), int(hit_y)))

        self.lines_of_sight_by_player[str(pid)] = rays
        # update last position/version
        self.last_positions[str(pid)] = (int(x), int(y))
        self.last_obstacles_version = self.obstacles_version

    def draw_rays(self, pid: str) -> None:
        """Draw stored rays for pid (fast)."""
        rays = self.lines_of_sight_by_player.get(str(pid), [])
        if not rays or not self.canvas:
            return
        for ox, oy, hx, hy in rays:
            self.canvas.create_line(ox, oy, hx, hy, fill="red", width=1)

    def draw(self, state: dict[str, Any]) -> None:
        self.canvas.delete("all")
        # draw obstacles first so rays respect occlusion
        self.draw_random_obstacles()
        self.draw_players(state)
        self.root.update_idletasks()
        self.root.update()

    def update_visibility(
        self,
        state: dict[str, Any],
        client_id: str,
        memory,
        fov_deg: float = 90.0,
        radius: float = 10.0,
        dir_angle: float = 0.0,
    ) -> None:
        """Server-side visibility: compute which players the server says are in
        the client's cone and update `memory` (StateMemory) accordingly.
        """
        positions = state.get("positions", {})
        client_pos = positions.get(client_id)
        if client_pos is None:
            return
        cx, cy, _ = client_pos

        # use rays previously computed for this client to determine visibility
        rays = self.lines_of_sight_by_player.get(str(client_id), [])

        def point_visible_by_rays(px: float, py: float) -> bool:
            # px,py are pixels
            for ox, oy, hx, hy in rays:
                rx = hx - ox
                ry = hy - oy
                rlen2 = rx * rx + ry * ry
                if rlen2 == 0:
                    continue
                # projection t of point onto ray (0..1 range is between origin and hit)
                t = ((px - ox) * rx + (py - oy) * ry) / rlen2
                if t < 0 or t > 1:
                    continue
                # closest point
                cxp = ox + rx * t
                cyp = oy + ry * t
                # distance from point to ray
                d2 = (px - cxp) ** 2 + (py - cyp) ** 2
                # threshold: half cell in pixels
                thresh = (self.tamanho_celula * 0.6) ** 2
                if d2 <= thresh:
                    return True
            return False

        for pid, pos in positions.items():
            if pid == client_id:
                if memory is not None:
                    memory.update_state(pid, {"level": "full", "pos": pos})
                continue
            x, y, z = pos
            px = x * self.tamanho_celula + self.tamanho_celula / 2
            py = y * self.tamanho_celula + self.tamanho_celula / 2
            visible = point_visible_by_rays(px, py)
            if not visible:
                if memory is not None:
                    memory.update_state(pid, {"level": "none"})
                continue
            dist = math.hypot(x - cx, y - cy)
            if dist <= radius * 0.33:
                info = {"level": "full", "pos": (x, y, z)}
            elif dist <= radius * 0.66:
                info = {"level": "partial", "pos": (round(x), round(y))}
            else:
                info = {"level": "position_only", "pos": (round(x), round(y))}
            if memory is not None:
                memory.update_state(pid, info)