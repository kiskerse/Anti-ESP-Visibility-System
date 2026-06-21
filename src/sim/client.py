"""
Cliente renderiza apenas o ClientPacket entregue pelo servidor.

Conhece: aliados (sempre), inimigos visíveis (full), ghosts DR (none+predicted_px).
NÃO conhece: inimigos fora do LOS, state bruto, StateMemory.
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from security.state import ClientPacket

FADE_TICKS = 10


class Client:

    def __init__(
        self,
        pid:       str,
        cell_size: int = 20,
        map_w:     int = 60,
        map_h:     int = 60,
        fps:       int = 60,
        team:      str = "team_a",
    ) -> None:
        self.pid       = pid
        self.cell_size = cell_size
        self.team      = team
        self._packet: ClientPacket | None = None

        self._display_px:  dict[str, tuple[float, float]] = {}
        self._fade:        dict[str, int] = {}
        self._last_px:     dict[str, tuple[float, float]] = {}

        self.root = tk.Toplevel()
        self.root.title(f"Cliente — {pid}  ({team})")
        w, h = map_w * cell_size, map_h * cell_size
        self.canvas = tk.Canvas(self.root, width=w, height=h, bg="#0d0d0d")
        self.canvas.pack()

        self._running  = True
        self._interval = int(max(1, 1000 / fps))
        self._loop()

    def deliver_packet(self, packet: "ClientPacket") -> None:
        self._packet = packet

    def _lerp(self, cur, target, t):
        return (cur[0] + (target[0] - cur[0]) * t,
                cur[1] + (target[1] - cur[1]) * t)

    def _draw(self) -> None:
        if self._packet is None:
            return
        p  = self._packet
        cs = self.cell_size
        self.canvas.delete("all")

        # obstáculos
        for obs in p.obstacles:
            ox, oy, ow, oh, *_ = obs
            self.canvas.create_rectangle(
                ox * cs, oy * cs, (ox + ow) * cs, (oy + oh) * cs,
                fill="#333", outline="#555",
            )

        # smokes (visíveis para todos)
        for s in p.smokes:
            px = s["cx"] * cs
            py = s["cy"] * cs
            r  = s["radius"] * cs
            self.canvas.create_oval(px - r, py - r, px + r, py + r,
                                    fill="#557777", outline="#88aaaa", stipple="gray50")

        r_dot = max(3, cs // 3)

        # self não está nos entries (servidor o removeu dos aliados do próprio player)
        # posição do self vem sempre do estado local (nunca é filtrada)

        # aliados (sempre visíveis)
        for apid, apos in p.allies.items():
            ax, ay, *_ = apos
            apx = ax * cs + cs / 2
            apy = ay * cs + cs / 2
            # azul para team_a, verde para team_b dependendo do time do cliente
            color = "#4488ff" if self.team == "team_a" else "#44ff88"
            self.canvas.create_oval(apx - r_dot, apy - r_dot, apx + r_dot, apy + r_dot,
                                    fill=color, outline="white")
            self.canvas.create_text(apx, apy - r_dot - 3, text=apid[-2:],
                                    fill="white", font=("Courier", 6))

        # inimigos
        for epid in p.all_enemy_pids():
            level  = p.level(epid)
            pos    = p.pos(epid)
            dr_px  = p.get(epid).get("predicted_px")

            if level == "full" and pos is not None:
                raw_px = (pos[0] * cs + cs / 2, pos[1] * cs + cs / 2)
                target = dr_px if dr_px else raw_px
                cur    = self._display_px.get(epid, target)
                dist   = math.hypot(target[0] - cur[0], target[1] - cur[1])
                t      = min(0.9, 0.25 + dist / (cs * 5))
                nx, ny = self._lerp(cur, target, t)
                self._display_px[epid] = (nx, ny)
                self._last_px[epid]    = (nx, ny)
                self._fade.pop(epid, None)
                color = "#ff4444" if self.team == "team_a" else "#ff8844"
                self.canvas.create_oval(nx - r_dot, ny - r_dot, nx + r_dot, ny + r_dot,
                                        fill=color, outline="white")
                self.canvas.create_text(nx, ny - r_dot - 3, text=epid[-2:],
                                        fill="white", font=("Courier", 6))

            elif level == "none":
                self._display_px.pop(epid, None)
                if dr_px is not None:
                    dpx, dpy = dr_px
                    self._last_px[epid] = (dpx, dpy)
                    self._fade.pop(epid, None)
                    self.canvas.create_oval(dpx - r_dot, dpy - r_dot,
                                            dpx + r_dot, dpy + r_dot,
                                            fill="#662222", outline="#444", dash=(2, 3))
                else:
                    ticks_left = self._fade.get(epid, FADE_TICKS)
                    last = self._last_px.get(epid)
                    if last and ticks_left > 0:
                        a = int(ticks_left / FADE_TICKS * 0x66)
                        col = f"#{a:02x}0000"
                        lx, ly = last
                        self.canvas.create_oval(lx - r_dot, ly - r_dot,
                                                lx + r_dot, ly + r_dot,
                                                fill=col, outline="#222", dash=(1, 4))
                        self._fade[epid] = ticks_left - 1
                    else:
                        self._fade.pop(epid, None)
                        self._last_px.pop(epid, None)

        self._draw_legend()

    def _draw_legend(self) -> None:
        cs = self.cell_size
        items = [
            ("■ Aliado",         "#4488ff" if self.team == "team_a" else "#44ff88"),
            ("■ Inimigo (LOS)",  "#ff4444"),
            ("⋯ Ghost DR",       "#662222"),
            ("○ Smoke",          "#557777"),
        ]
        y0 = 4
        for label, color in items:
            self.canvas.create_text(4, y0, text=label, fill=color, anchor="nw",
                                    font=("Courier", 7))
            y0 += 11

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
