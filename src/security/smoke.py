"""
Sistema de Smokes — bloqueio dinâmico de LOS.

Smokes sobrescrevem o PVS estático: mesmo que o PVS diga que A vê B,
se uma smoke estiver no caminho o servidor trata como "none".

Implementação:
  - Smoke = círculo de raio R em posição (cx, cy) no espaço de células
  - Para cada tick, o servidor verifica se o segmento observer→target
    passa por alguma smoke ativa antes de consultar o PVS
  - Smokes têm duração (decaem após `duration_ticks` ticks)

Escalabilidade:
  - Número típico de smokes simultâneas: 3–6 por rodada no Valorant
  - Para cada par (obs, target), a verificação é O(n_smokes) segmento-círculo
  - Com n_smokes ≤ 10, o overhead é desprezível
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Smoke:
    """Uma smoke ativa no mapa."""
    cx: float          # centro X em coordenadas de célula
    cy: float          # centro Y
    radius: float      # raio em células
    duration_ticks: int
    ticks_remaining: int = field(init=False)
    smoke_id: int = field(default=0)

    def __post_init__(self) -> None:
        self.ticks_remaining = self.duration_ticks

    def tick(self) -> bool:
        """Avança um tick. Retorna True se a smoke ainda está ativa."""
        self.ticks_remaining -= 1
        return self.ticks_remaining > 0

    @property
    def active(self) -> bool:
        return self.ticks_remaining > 0


class SmokeSystem:
    """Gerencia smokes ativas e verifica bloqueio de LOS."""

    def __init__(self) -> None:
        self._smokes: list[Smoke] = []
        self._next_id = 0

    def add_smoke(self, cx: float, cy: float, radius: float, duration_ticks: int) -> int:
        s = Smoke(cx=cx, cy=cy, radius=radius, duration_ticks=duration_ticks,
                  smoke_id=self._next_id)
        self._smokes.append(s)
        self._next_id += 1
        return s.smoke_id

    def tick(self) -> None:
        """Remove smokes expiradas."""
        self._smokes = [s for s in self._smokes if s.tick()]

    def active_smokes(self) -> list[Smoke]:
        return [s for s in self._smokes if s.active]

    def blocks_los(
        self,
        ox: float, oy: float,   # observador (centro da célula, em coords de célula)
        tx: float, ty: float,   # alvo
    ) -> bool:
        """Verifica se alguma smoke bloqueia o segmento obs→target.

        Usa interseção segmento-círculo: O(n_smokes) por par.
        """
        dx = tx - ox
        dy = ty - oy
        seg_len2 = dx * dx + dy * dy
        if seg_len2 == 0:
            return False

        for smoke in self._smokes:
            if not smoke.active:
                continue
            # projeção do centro da smoke no segmento
            fx = smoke.cx - ox
            fy = smoke.cy - oy
            t = (fx * dx + fy * dy) / seg_len2
            t = max(0.0, min(1.0, t))
            # ponto mais próximo no segmento
            px = ox + t * dx
            py = oy + t * dy
            dist2 = (smoke.cx - px) ** 2 + (smoke.cy - py) ** 2
            if dist2 <= smoke.radius ** 2:
                return True
        return False

    def get_snapshot(self) -> list[dict]:
        """Snapshot para o cliente (posição e raio são públicos e smokes são visíveis)."""
        return [
            {"cx": s.cx, "cy": s.cy, "radius": s.radius,
             "ticks_remaining": s.ticks_remaining, "smoke_id": s.smoke_id}
            for s in self._smokes if s.active
        ]
