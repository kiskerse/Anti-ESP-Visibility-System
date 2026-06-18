from __future__ import annotations

import math
import random
import tkinter as tk
from typing import Any, List

from security.state import StateMemory


class Game:
    """Servidor — única fonte de verdade.

    Modelo de visibilidade (inspirado em Valorant):
    - Se o inimigo está na linha de visão (qualquer distância) → posição EXATA
    - Se não está → NADA (none)

    Não existe zona "partial" baseada em distância.
    A distância só afeta se o raycasting detecta o alvo, não o que é revelado.
    O dead-reckoning no StateMemory cuida de suavizar saídas do FOV (anti pop-in).
    """

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
        self.n_rays = config.get("n_rays", 360)   # default alto para não perder alvos próximos
        self.ui = create_ui
        self.root = None
        self.canvas = None
        if self.ui:
            self.root = tk.Toplevel()
            self.root.title("Server View (omnisciente)")
            self.canvas = tk.Canvas(
                self.root,
                width=self.largura,
                height=self.altura,
                bg="black",
            )
            self.canvas.pack()

        self.obstaculos: List[tuple] = config.get("obstaculos", [])
        self.lines_of_sight_by_player: dict[str, list[tuple[int, int, int, int]]] = {}
        self.last_positions: dict[str, tuple[int, int]] = {}
        self.obstacles_version = 0
        self.last_obstacles_version = 0

    # ------------------------------------------------------------------
    # Obstáculos
    # ------------------------------------------------------------------

    def _generate_obstacle(self) -> tuple:
        cols = self.largura // self.tamanho_celula
        rows = self.altura // self.tamanho_celula
        x = random.randint(0, cols - 1)
        y = random.randint(0, rows - 1)
        w = random.randint(max(1, cols // 12), max(1, cols // 6))
        h = random.randint(max(1, rows // 12), max(1, rows // 6))
        return (x, y, w, h, "grey", "solid")

    def draw_random_obstacles(self) -> None:
        if not self.obstaculos:
            for _ in range(random.randint(5, 15)):
                self.obstaculos.append(self._generate_obstacle())
            self.obstacles_version += 1
        if self.canvas:
            self._redraw_obstacles()

    def _redraw_obstacles(self) -> None:
        if not self.canvas:
            return
        for obs in self.obstaculos:
            x, y, w, h, cor, estilo = obs
            x1, y1 = x * self.tamanho_celula, y * self.tamanho_celula
            x2, y2 = (x + w) * self.tamanho_celula, (y + h) * self.tamanho_celula
            fill = cor if estilo == "solid" else ""
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=cor)

    def _hits_obstacle(self, px: float, py: float) -> bool:
        gx = px / self.tamanho_celula
        gy = py / self.tamanho_celula
        for obs in self.obstaculos:
            ox, oy, ow, oh, *_ = obs
            if ox <= gx <= ox + ow and oy <= gy <= oy + oh:
                return True
        return False

    # ------------------------------------------------------------------
    # Raycasting
    # ------------------------------------------------------------------

    def compute_lines_of_sight(self, pid: str, pos: tuple) -> None:
        max_dist = max(self.largura, self.altura)
        step = max(2, self.tamanho_celula // 8)   # passo fino para não "vazar" atrás de paredes
        x, y, *_ = pos
        ox = x * self.tamanho_celula + self.tamanho_celula / 2
        oy = y * self.tamanho_celula + self.tamanho_celula / 2
        rays: list[tuple[int, int, int, int]] = []
        for i in range(self.n_rays):
            angle = (2 * math.pi * i) / self.n_rays
            dx, dy = math.cos(angle), math.sin(angle)
            hx, hy = ox + max_dist * dx, oy + max_dist * dy
            dist = 0.0
            while dist <= max_dist:
                sx, sy = ox + dx * dist, oy + dy * dist
                if sx < 0 or sx > self.largura or sy < 0 or sy > self.altura:
                    hx, hy = sx, sy
                    break
                if self._hits_obstacle(sx, sy):
                    hx, hy = sx, sy
                    break
                dist += step
            rays.append((int(ox), int(oy), int(hx), int(hy)))
        self.lines_of_sight_by_player[str(pid)] = rays
        self.last_positions[str(pid)] = (int(x), int(y))
        self.last_obstacles_version = self.obstacles_version

    def _draw_rays(self, pid: str) -> None:
        if not self.canvas:
            return
        for ox, oy, hx, hy in self.lines_of_sight_by_player.get(str(pid), []):
            self.canvas.create_line(ox, oy, hx, hy, fill="#330000", width=1)

    # ------------------------------------------------------------------
    # Visibilidade — lógica Valorant-like
    # ------------------------------------------------------------------

    def _is_visible(self, rays: list, px: float, py: float) -> bool:
        """Verifica se o ponto (px, py) é coberto por algum raio.

        Threshold menor que o antigo para evitar falsos positivos
        atrás de paredes finas.
        """
        thresh = (self.tamanho_celula * 0.45) ** 2
        for ox, oy, hx, hy in rays:
            rx, ry = hx - ox, hy - oy
            rlen2 = rx * rx + ry * ry
            if rlen2 == 0:
                continue
            t = ((px - ox) * rx + (py - oy) * ry) / rlen2
            if t < 0 or t > 1:
                continue
            cxp = ox + rx * t
            cyp = oy + ry * t
            if (px - cxp) ** 2 + (py - cyp) ** 2 <= thresh:
                return True
        return False

    # ------------------------------------------------------------------
    # Tick do servidor
    # ------------------------------------------------------------------

    def tick(
        self,
        state: dict[str, Any],
        client_id: str,
        memory: StateMemory,
        radius: float = 999.0,   # sem limite de distância por padrão (Valorant-like)
    ) -> None:
        """Executa um tick:
        1. Recomputa raios se o jogador moveu
        2. Classifica cada inimigo: visível → full exato | não visível → none
        3. Escreve na StateMemory (cliente nunca toca aqui)
        """
        positions = state.get("positions", {})
        client_pos = positions.get(client_id)
        if client_pos is None:
            return

        cx, cy, *_ = client_pos
        last = self.last_positions.get(str(client_id))
        if last != (int(cx), int(cy)) or self.last_obstacles_version != self.obstacles_version:
            self.compute_lines_of_sight(client_id, client_pos)

        rays = self.lines_of_sight_by_player.get(str(client_id), [])

        for pid, pos in positions.items():
            x, y, *rest = pos
            z = rest[0] if rest else 0

            if pid == client_id:
                memory.update(pid, "full", (x, y, z))
                continue

            # centro do boneco em pixels
            px = x * self.tamanho_celula + self.tamanho_celula / 2
            py = y * self.tamanho_celula + self.tamanho_celula / 2

            if self._is_visible(rays, px, py):
                # VISÍVEL → posição exata, sem gradação por distância
                memory.update(pid, "full", (x, y, z))
            else:
                # NÃO VISÍVEL → nada (DR cuida do anti pop-in)
                memory.update(pid, "none", None)

        memory.set_obstacles(self.obstaculos)

    # ------------------------------------------------------------------
    # Desenho servidor (omnisciente)
    # ------------------------------------------------------------------

    def draw(self, state: dict[str, Any]) -> None:
        if not self.canvas or not self.root:
            return
        self.canvas.delete("all")
        self._redraw_obstacles()
        # raios do player1 (semi-transparente para não poluir)
        self._draw_rays("player1")
        for pid, pos in state["positions"].items():
            x, y, *_ = pos
            cx = x * self.tamanho_celula + self.tamanho_celula / 2
            cy = y * self.tamanho_celula + self.tamanho_celula / 2
            r = max(4, self.tamanho_celula // 4)
            color = "red" if str(pid).startswith("enemy") else "cyan"
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=color)
            lbl_color = "white"
            self.canvas.create_text(cx, cy - r - 4, text=str(pid), fill=lbl_color, font=("Courier", 7))
        self.root.update_idletasks()
        self.root.update()

    # Alias para compatibilidade com benchmark
    def update_visibility(self, state, client_id, memory, fov_deg=90.0, radius=999.0, dir_angle=0.0):
        self.tick(state, client_id, memory, radius)
