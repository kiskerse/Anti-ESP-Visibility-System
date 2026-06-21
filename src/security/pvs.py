"""
PVS — Potentially Visible Set  (Valorant-like)

Build offline com numpy vectorizado + cache em disco (pickle comprimido).
Na segunda execução carrega localmente

Complexidade:
  Build:   O(N_walkable²)  — pago uma vez, salvo em cache
  Cache:   load O(1) leitura de arquivo
  Runtime: O(1) por lookup — frozenset hash
"""

from __future__ import annotations

import gzip
import os
import pickle
import time
from typing import NamedTuple

import numpy as np


class Cell(NamedTuple):
    x: int
    y: int


class PVSBuilder:

    def __init__(self, map_w: int, map_h: int, obstacles: list[tuple]) -> None:
        self.W = map_w
        self.H = map_h
        self._solid = np.zeros((map_h, map_w), dtype=bool)
        for (ox, oy, ow, oh, *_) in obstacles:
            x1 = max(0, ox);  x2 = min(map_w, ox + ow)
            y1 = max(0, oy);  y2 = min(map_h, oy + oh)
            self._solid[y1:y2, x1:x2] = True

    def _batch_ray_clear(
        self,
        ox: float, oy: float,
        txs: np.ndarray, tys: np.ndarray,
        samples: int = 32,
    ) -> np.ndarray:
        N = len(txs)
        if N == 0:
            return np.array([], dtype=bool)
        t_vals  = np.linspace(0.0, 1.0, samples, dtype=np.float32)
        dest_x  = txs.astype(np.float32) + 0.5
        dest_y  = tys.astype(np.float32) + 0.5
        xs = ox + t_vals[:, None] * (dest_x[None, :] - ox)
        ys = oy + t_vals[:, None] * (dest_y[None, :] - oy)
        gx   = np.clip(xs.astype(np.int32), 0, self.W - 1)
        gy   = np.clip(ys.astype(np.int32), 0, self.H - 1)
        hits = self._solid[gy, gx]
        return ~np.any(hits, axis=0)

    def build(self, progress: bool = True) -> dict[Cell, frozenset[Cell]]:
        W, H  = self.W, self.H
        solid = self._solid
        all_y, all_x = np.mgrid[0:H, 0:W]
        walk_mask = ~solid
        wx = all_x[walk_mask].astype(np.int32)
        wy = all_y[walk_mask].astype(np.int32)
        N  = len(wx)

        pvs_bits = np.zeros((N, N), dtype=bool)
        np.fill_diagonal(pvs_bits, True)

        t0      = time.perf_counter()
        offsets = [(0.5,0.5),(0.1,0.1),(0.9,0.1),(0.1,0.9),(0.9,0.9)]
        BATCH   = 64

        for start in range(0, N, BATCH):
            end = min(start + BATCH, N)
            for i in range(start, end):
                j_rest = np.arange(i + 1, N)
                if len(j_rest) == 0:
                    continue
                txs = wx[j_rest]
                tys = wy[j_rest]
                visible = np.zeros(len(j_rest), dtype=bool)
                for dox, doy in offsets:
                    if np.all(visible):
                        break
                    visible |= self._batch_ray_clear(wx[i]+dox, wy[i]+doy, txs, tys)
                pvs_bits[i, j_rest[visible]] = True
                pvs_bits[j_rest[visible], i] = True

            if progress:
                done = min(end, N)
                el   = time.perf_counter() - t0
                eta  = (el / done) * (N - done) if done else 0
                print(f"  PVS: {done/N*100:.0f}%  {el:.1f}s  ETA {eta:.1f}s     ", end="\r")

        if progress:
            print(f"\n  PVS build: {N} células em {time.perf_counter()-t0:.2f}s")

        # converte para dict de frozensets
        pvs: dict[Cell, frozenset[Cell]] = {}
        for y in range(H):
            for x in range(W):
                if solid[y, x]:
                    pvs[Cell(x, y)] = frozenset()
        walk_cells = [Cell(int(wx[i]), int(wy[i])) for i in range(N)]
        for i in range(N):
            vis = np.where(pvs_bits[i])[0]
            pvs[walk_cells[i]] = frozenset(walk_cells[j] for j in vis)
        return pvs


class PVSIndex:
    """Lookup O(1) em runtime + cache em disco."""

    def __init__(self, pvs: dict[Cell, frozenset[Cell]]) -> None:
        self._pvs = pvs

    # Cache em disco (gzip+pickle)

    def save(self, path: str) -> None:
        """Salva PVS em cache comprimido. Próxima carga em < 1s."""
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with gzip.open(path, "wb", compresslevel=3) as f:
            pickle.dump(self._pvs, f, protocol=pickle.HIGHEST_PROTOCOL)
        size_kb = os.path.getsize(path) / 1024
        print(f"  PVS cache salvo: {path}  ({size_kb:.0f} KB)")

    @classmethod
    def load(cls, path: str) -> "PVSIndex":
        """Carrega PVS de cache. Lança FileNotFoundError se não existir."""
        with gzip.open(path, "rb") as f:
            pvs = pickle.load(f)
        return cls(pvs)

    # API de runtime

    def visible_from(self, observer: Cell) -> frozenset[Cell]:
        return self._pvs.get(observer, frozenset())

    def can_see(self, observer: Cell, target: Cell) -> bool:
        return target in self._pvs.get(observer, frozenset())

    def stats(self) -> dict:
        sizes = [len(v) for v in self._pvs.values() if v]
        if not sizes:
            return {}
        return {
            "cells":       len(self._pvs),
            "walkable":    len(sizes),
            "avg_visible": round(sum(sizes) / len(sizes), 1),
            "min_visible": min(sizes),
            "max_visible": max(sizes),
        }


def load_or_build(
    map_w: int,
    map_h: int,
    obstacles: list[tuple],
    cache_path: str,
    progress: bool = True,
) -> PVSIndex:
    """Carrega cache se existir, senão constrói e salva."""
    if os.path.exists(cache_path):
        t0 = time.perf_counter()
        idx = PVSIndex.load(cache_path)
        print(f"  PVS carregado do cache: {cache_path}  ({(time.perf_counter()-t0)*1000:.0f}ms)")
        return idx
    builder = PVSBuilder(map_w, map_h, obstacles)
    pvs     = builder.build(progress=progress)
    idx     = PVSIndex(pvs)
    idx.save(cache_path)
    return idx
