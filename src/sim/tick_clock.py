"""
Usa acumulação de perf_counter em vez de sleep fixo, o que evita
drift de sleep_granularity (Windows: ~15ms, Linux: ~1ms).

Padrão de uso:
    clock = TickClock(target_tps=128)
    clock.start()
    while running:
        clock.wait_next_tick()
        game.tick(...)
        clock.end_tick()

Métricas disponíveis:
    clock.achieved_tps      → TPS real dos últimos N ticks
    clock.tick_budget_ms    → budget por tick (1000/128 = 7.8125ms)
    clock.last_tick_ms      → tempo do último tick
    clock.missed_ticks      → ticks que excederam o budget
    clock.jitter_ms         → desvio padrão dos intervalos de tick
"""

from __future__ import annotations

import statistics
import time


class TickClock:

    def __init__(self, target_tps: int = 128, history: int = 128) -> None:
        self.target_tps     = target_tps
        self.tick_budget_s  = 1.0 / target_tps
        self.tick_budget_ms = self.tick_budget_s * 1000.0
        self._history       = history

        self._next_tick_t   = 0.0
        self._tick_start_t  = 0.0
        self._intervals:    list[float] = []   # inter-tick (ms)
        self._compute_ms:   list[float] = []   # compute por tick
        self._missed        = 0
        self._total         = 0

    def start(self) -> None:
        self._next_tick_t = time.perf_counter()

    def wait_next_tick(self) -> None:
        """Aguarda o próximo tick sem drift (spin-wait preciso)."""
        # spin-wait nos últimos 0.5ms para precisão máxima
        sleep_until = self._next_tick_t - 0.0005
        now = time.perf_counter()
        if sleep_until > now:
            time.sleep(sleep_until - now)
        # spin final
        while time.perf_counter() < self._next_tick_t:
            pass
        self._tick_start_t = time.perf_counter()

    def end_tick(self) -> None:
        """Registra métricas e agenda próximo tick."""
        now = time.perf_counter()
        compute_ms = (now - self._tick_start_t) * 1000.0
        self._compute_ms.append(compute_ms)

        # intervalo desde o início do tick anterior
        if self._intervals:
            interval = (self._tick_start_t - self._prev_tick_start) * 1000.0
            self._intervals.append(interval)

        self._prev_tick_start = self._tick_start_t
        self._total += 1
        if compute_ms > self.tick_budget_ms:
            self._missed += 1

        # mantém histórico limitado
        if len(self._intervals) > self._history:
            self._intervals.pop(0)
        if len(self._compute_ms) > self._history:
            self._compute_ms.pop(0)

        # próximo tick com acumulação (sem drift)
        self._next_tick_t += self.tick_budget_s

    @property
    def achieved_tps(self) -> float:
        if len(self._intervals) < 2:
            return 0.0
        avg_interval_s = statistics.mean(self._intervals) / 1000.0
        return 1.0 / avg_interval_s if avg_interval_s > 0 else 0.0

    @property
    def last_compute_ms(self) -> float:
        return self._compute_ms[-1] if self._compute_ms else 0.0

    @property
    def avg_compute_ms(self) -> float:
        return statistics.mean(self._compute_ms) if self._compute_ms else 0.0

    @property
    def jitter_ms(self) -> float:
        return statistics.stdev(self._intervals) if len(self._intervals) > 1 else 0.0

    @property
    def missed_ticks(self) -> int:
        return self._missed

    @property
    def missed_pct(self) -> float:
        return self._missed / max(self._total, 1) * 100.0

    def stats(self) -> dict:
        return {
            "target_tps":    self.target_tps,
            "achieved_tps":  round(self.achieved_tps, 1),
            "tick_budget_ms": round(self.tick_budget_ms, 4),
            "avg_compute_ms": round(self.avg_compute_ms, 4),
            "jitter_ms":      round(self.jitter_ms, 3),
            "missed_ticks":   self.missed_ticks,
            "missed_pct":     round(self.missed_pct, 2),
            "overhead_pct":   round(self.avg_compute_ms / self.tick_budget_ms * 100, 3),
        }
