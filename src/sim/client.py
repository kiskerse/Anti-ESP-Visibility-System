from __future__ import annotations

import math
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from security.state import ClientPacket


class Client:
    """Cliente — renderiza APENAS o ClientPacket entregue pelo servidor.

    Sem acesso a StateMemory, state bruto ou qualquer dado não autorizado.
    O servidor chama deliver_packet() a cada tick.

    Anti pop-in:
    - Ao receber "full": lerp suave em direção à posição alvo (DR prevista ou exata)
    - Ao receber "none" com predicted_px: ghost desbotado na posição DR
    - Ao receber "none" sem predicted_px: fade out gradual antes de sumir
    """

    FADE_TICKS = 8   # ticks de fade out antes de sumir completamente

    def __init__(
        self,
        client_id: str,
        cell_size: int = 50,
        map_w: int = 20,
        map_h: int = 20,
        fps: int = 60,
    ) -> None:
        self.client_id = client_id
        self.cell_size = cell_size
        self._packet: ClientPacket | None = None

        # posições de display em pixels (para lerp suave)
        self._display_px: dict[str, tuple[float, float]] = {}
        # velocidade de display (para inércia visual)
        self._display_vel: dict[str, tuple[float, float]] = {}
        # fade out: ticks restantes quando um jogador sai do FOV sem DR
        self._fade: dict[str, int] = {}
        # última posição de display conhecida (para fade out)
        self._last_px: dict[str, tuple[float, float]] = {}

        self.root = tk.Toplevel()
        self.root.title(f"Client — {client_id}")
        w, h = map_w * cell_size, map_h * cell_size
        self.canvas = tk.Canvas(self.root, width=w, height=h, bg="black")
        self.canvas.pack()

        self._running = True
        self._interval = int(max(1, 1000 / fps))
        self._loop()

    # ------------------------------------------------------------------
    # Interface pública — servidor chama isso
    # ------------------------------------------------------------------

    def deliver_packet(self, packet: "ClientPacket") -> None:
        self._packet = packet

    # ------------------------------------------------------------------
    # Renderização
    # ------------------------------------------------------------------

    def _lerp(self, cur: tuple[float, float], target: tuple[float, float], t: float) -> tuple[float, float]:
        return (cur[0] + (target[0] - cur[0]) * t, cur[1] + (target[1] - cur[1]) * t)

    def _draw(self) -> None:
        if self._packet is None:
            return
        packet = self._packet
        self.canvas.delete("all")
        cs = self.cell_size

        # obstáculos
        for obs in packet.obstacles:
            ox, oy, ow, oh, cor, estilo = obs
            x1, y1 = ox * cs, oy * cs
            x2, y2 = (ox + ow) * cs, (oy + oh) * cs
            fill = cor if estilo == "solid" else ""
            self.canvas.create_rectangle(x1, y1, x2, y2, fill=fill, outline=cor)

        r = max(4, cs // 4)
        active_pids = set(packet.all_pids())

        for pid in active_pids:
            level   = packet.level(pid)
            pos     = packet.pos(pid)
            dr_px   = packet.get(pid).get("predicted_px")
            is_enemy = str(pid).startswith("enemy")

            # ---- self ----
            if pid == self.client_id:
                if pos is None:
                    continue
                px = pos[0] * cs + cs / 2
                py = pos[1] * cs + cs / 2
                self.canvas.create_oval(px - r, py - r, px + r, py + r, fill="cyan")
                self._display_px[pid] = (px, py)
                self._fade.pop(pid, None)
                continue

            # ---- full (visível com posição exata) ----
            if level == "full" and pos is not None:
                raw_px = (pos[0] * cs + cs / 2, pos[1] * cs + cs / 2)
                # target: DR previsto (mais suave) ou posição exata
                target = dr_px if dr_px is not None else raw_px

                cur = self._display_px.get(pid, target)
                # lerp adaptativo: mais rápido quando longe (evita lag perceptível)
                dist = math.hypot(target[0] - cur[0], target[1] - cur[1])
                t = min(0.9, 0.3 + dist / (cs * 4))
                nx, ny = self._lerp(cur, target, t)

                self._display_px[pid] = (nx, ny)
                self._last_px[pid] = (nx, ny)
                self._fade.pop(pid, None)   # cancela fade se voltou ao FOV

                color = "red" if is_enemy else "green"
                self.canvas.create_oval(nx - r, ny - r, nx + r, ny + r, fill=color)
                # label de debug (pequeno)
                self.canvas.create_text(nx, ny - r - 4, text=str(pid), fill="white", font=("Courier", 7))
                continue

            # ---- none ----
            if level == "none":
                self._display_px.pop(pid, None)

                if dr_px is not None:
                    # Ghost DR: o servidor ainda tem extrapolação válida
                    color = "#880000" if is_enemy else "#008800"
                    dpx, dpy = dr_px
                    self._last_px[pid] = (dpx, dpy)
                    self._fade.pop(pid, None)
                    self.canvas.create_oval(
                        dpx - r, dpy - r, dpx + r, dpy + r,
                        fill=color, outline="#555", dash=(2, 3),
                    )
                else:
                    # DR expirou — fade out gradual para evitar desaparecimento brusco
                    ticks_left = self._fade.get(pid, self.FADE_TICKS)
                    last = self._last_px.get(pid)
                    if last is not None and ticks_left > 0:
                        alpha_ratio = ticks_left / self.FADE_TICKS
                        # simula fade via cor mais escura a cada tick
                        level_hex = int(alpha_ratio * 0x88)
                        hex_str = f"#{level_hex:02x}0000" if is_enemy else f"#00{level_hex:02x}00"
                        lx, ly = last
                        self.canvas.create_oval(
                            lx - r, ly - r, lx + r, ly + r,
                            fill=hex_str, outline="#333", dash=(1, 4),
                        )
                        self._fade[pid] = ticks_left - 1
                    else:
                        # sumiu completamente
                        self._fade.pop(pid, None)
                        self._last_px.pop(pid, None)

        self._draw_legend()

    def _draw_legend(self) -> None:
        items = [
            ("■ Você",                     "cyan"),
            ("■ Inimigo (visível)",         "red"),
            ("■ Aliado (visível)",          "green"),
            ("⋯ Ghost DR (saindo FOV)",     "#880000"),
            ("⋯ Fade out (DR expirado)",    "#440000"),
        ]
        y0 = 6
        for label, color in items:
            self.canvas.create_text(8, y0, text=label, fill=color, anchor="nw", font=("Courier", 8))
            y0 += 12

    def _loop(self) -> None:
        if not self._running:
            return
        try:
            self._draw()
        except Exception:
            pass
        self.root.after(self._interval, self._loop)

    def stop(self) -> None:
        self._running = False
        try:
            self.root.destroy()
        except Exception:
            pass
