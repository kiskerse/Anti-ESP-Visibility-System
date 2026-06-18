"""
Wallhack ESP, simulação de cheat para medir a vantagem real.

O que este módulo simula:
- Um cheat que lê diretamente o state bruto do servidor (como seria sem proteção)
- Desenha APENAS os bonecos dos inimigos, sem paredes ou mapa (ESP clássico)
- Mede a "vantagem wallhack": quantos inimigos estão visíveis via cheat
  mas NÃO estão visíveis pelo sistema legítimo naquele tick

Com o sistema anti-wallhack ativo:
- O cheat leria apenas o ClientPacket (que já é filtrado)
- Então a "vantagem" cai drasticamente: só vê quem você já veria normalmente
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from security.state import ClientPacket


class WallhackESP:
    """
    Janela ESP que simula o que um wallhack veria.

    MODO PROTEGIDO (padrão):
        Lê o ClientPacket — o mesmo que o cliente legítimo recebe.
        Demonstra que o cheat NÃO ganha vantagem: só vê quem já estaria visível.

    MODO DESPROTEGIDO (sem_protecao=True):
        Lê o state bruto do servidor — simula um jogo sem este sistema.
        Mostra todos os inimigos independentemente de obstáculos.

    A diferença entre os dois modos é a vantagem medida.
    """

    def __init__(
        self,
        cell_size: int = 50,
        map_w: int = 20,
        map_h: int = 20,
        fps: int = 60,
        sem_protecao: bool = False,
    ) -> None:
        self.cell_size = cell_size
        self.sem_protecao = sem_protecao

        # estado interno para modo desprotegido
        self._raw_state: dict[str, Any] | None = None
        # estado para modo protegido
        self._packet: ClientPacket | None = None

        # métricas de vantagem
        self.advantage_history: list[int] = []   # inimigos extras visíveis via cheat
        self.total_ticks = 0
        self.ticks_with_advantage = 0

        self.root = tk.Toplevel()
        mode_str = "SEM proteção (cheat enxerga tudo)" if sem_protecao else "COM proteção (cheat filtrado)"
        self.root.title(f"Wallhack ESP — {mode_str}")
        self.root.configure(bg="#0a0a0a")

        # Canvas sem obstáculos — ESP típico só mostra bonecos
        w, h = map_w * cell_size, map_h * cell_size
        self.canvas = tk.Canvas(self.root, width=w, height=h, bg="#0a0a0a", highlightthickness=0)
        self.canvas.pack()

        self._running = True
        self._interval = int(max(1, 1000 / fps))
        self._loop()

    # API pública

    def deliver_packet(self, packet: "ClientPacket") -> None:
        """Alimenta o ESP com dados do modo PROTEGIDO (ClientPacket filtrado)."""
        self._packet = packet

    def deliver_raw_state(self, state: dict[str, Any], visible_by_legit: set[str]) -> None:
        """Alimenta o ESP com state bruto (modo DESPROTEGIDO).
        visible_by_legit: pids que o cliente legítimo já visualiza (para calcular vantagem).
        """
        self._raw_state = state
        self._visible_legit = visible_by_legit

    # Renderização

    def _draw(self) -> None:
        self.canvas.delete("all")
        cs = self.cell_size
        r = max(5, cs // 4)

        advantage = 0

        if self.sem_protecao and self._raw_state is not None:
            # MODO DESPROTEGIDO: vê TODOS os inimigos
            legit = getattr(self, "_visible_legit", set())
            for pid, pos in self._raw_state.get("positions", {}).items():
                if pid == "player1":
                    continue
                x, y, *_ = pos
                px = x * cs + cs / 2
                py = y * cs + cs / 2
                # vermelho brilhante = inimigo que o cheat revela ilegitimamente
                is_extra = pid not in legit
                color = "#ff0000" if is_extra else "#ff8800"
                outline = "#ffffff" if is_extra else "#ffaa00"
                self.canvas.create_oval(px - r, py - r, px + r, py + r,
                                        fill=color, outline=outline, width=2)
                if is_extra:
                    self.canvas.create_text(px, py - r - 6, text="ESP!", fill="#ff0000",
                                            font=("Courier", 8, "bold"))
                    advantage += 1

        elif not self.sem_protecao and self._packet is not None:
            # MODO PROTEGIDO: cheat vê apenas o ClientPacket filtrado
            for pid in self._packet.all_pids():
                if pid == "player1":
                    continue
                level = self._packet.level(pid)
                pos   = self._packet.pos(pid)
                dr_px = self._packet.get(pid).get("predicted_px")

                if level == "full" and pos is not None:
                    px = pos[0] * cs + cs / 2
                    py = pos[1] * cs + cs / 2
                    # laranja = visível pelo sistema legítimo também — sem vantagem aparente
                    self.canvas.create_oval(px - r, py - r, px + r, py + r,
                                            fill="#ff8800", outline="#ffaa00", width=2)
                elif level == "none" and dr_px is not None:
                    # ghost DR — posição extrapolada, imprecisa
                    dpx, dpy = dr_px
                    self.canvas.create_oval(dpx - r, dpy - r, dpx + r, dpy + r,
                                            fill="#553300", outline="#886600",
                                            width=1, dash=(2, 3))
                    self.canvas.create_text(dpx, dpy - r - 6, text="~DR", fill="#886600",
                                            font=("Courier", 7))
            advantage = 0  # com proteção, cheat não lê nada a mais

        # métricas
        self.total_ticks += 1
        self.advantage_history.append(advantage)
        if len(self.advantage_history) > 200:
            self.advantage_history.pop(0)
        if advantage > 0:
            self.ticks_with_advantage += 1

        avg_adv = sum(self.advantage_history) / max(len(self.advantage_history), 1)
        adv_pct = self.ticks_with_advantage / max(self.total_ticks, 1) * 100

        # HUD de métricas
        mode_str = "DESPROTEGIDO" if self.sem_protecao else "PROTEGIDO"
        color_mode = "#ff4444" if self.sem_protecao else "#44ff44"
        self.canvas.create_text(4, 4,
            text=f"MODO: {mode_str}",
            fill=color_mode, anchor="nw", font=("Courier", 9, "bold"))
        self.canvas.create_text(4, 18,
            text=f"Vantagem atual: {advantage} inimigos extras",
            fill="#ffff00", anchor="nw", font=("Courier", 8))
        self.canvas.create_text(4, 30,
            text=f"Média: {avg_adv:.1f}  |  Ticks c/ vantagem: {adv_pct:.1f}%",
            fill="#ffaa00", anchor="nw", font=("Courier", 8))

        if self.sem_protecao:
            self.canvas.create_text(4, 42,
                text="■ Laranja = já visível  ■ Vermelho = VANTAGEM CHEAT",
                fill="#aaaaaa", anchor="nw", font=("Courier", 7))
        else:
            self.canvas.create_text(4, 42,
                text="■ Laranja = visível legit  ⋯ Cinza = ghost DR (impreciso)",
                fill="#aaaaaa", anchor="nw", font=("Courier", 7))

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

    def get_stats(self) -> dict:
        avg_adv = sum(self.advantage_history) / max(len(self.advantage_history), 1)
        adv_pct = self.ticks_with_advantage / max(self.total_ticks, 1) * 100
        return {
            "avg_advantage": round(avg_adv, 2),
            "ticks_with_advantage_pct": round(adv_pct, 1),
            "total_ticks": self.total_ticks,
        }
