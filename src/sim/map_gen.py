"""
Gerador de mapa — produz layout denso com bastante obstáculos,
respeitando spawns livres para 10 jogadores.
"""
from __future__ import annotations

import random


def generate_map(
    map_w: int = 60,
    map_h: int = 60,
    n_obstacles: int = 45,
    seed: int | None = None,
) -> tuple[list[tuple], frozenset[tuple[int, int]]]:
    """Retorna (obstacles, solid_set)."""
    if seed is not None:
        random.seed(seed)

    obstacles: list[tuple] = []
    solid: set[tuple[int, int]] = set()

    # bordas do mapa
    for x in range(map_w):
        solid.add((x, 0)); solid.add((x, map_h - 1))
    for y in range(map_h):
        solid.add((0, y)); solid.add((map_w - 1, y))
    obstacles.append((0, 0, map_w, 1, "#666", "solid"))         # topo
    obstacles.append((0, map_h - 1, map_w, 1, "#666", "solid")) # base
    obstacles.append((0, 0, 1, map_h, "#666", "solid"))         # esquerda
    obstacles.append((map_w - 1, 0, 1, map_h, "#666", "solid")) # direita

    attempts = 0
    placed   = 0
    while placed < n_obstacles and attempts < n_obstacles * 30:
        attempts += 1
        # evita bordas de spawn (bordas do mapa)
        ox = random.randint(3, map_w - 6)
        oy = random.randint(3, map_h - 6)
        ow = random.randint(1, max(1, map_w // 10))
        oh = random.randint(1, max(1, map_h // 10))
        ow = min(ow, map_w - ox - 2)
        oh = min(oh, map_h - oy - 2)
        if ow <= 0 or oh <= 0:
            continue

        # não bloqueia área de spawn (cantos)
        if _overlaps_spawn_zones(ox, oy, ow, oh, map_w, map_h):
            continue

        # adiciona se não dobra cobertura excessiva
        new_cells = {(x, y) for x in range(ox, ox + ow) for y in range(oy, oy + oh)}
        if len(new_cells & solid) > len(new_cells) // 3:
            continue  # muita sobreposição

        obstacles.append((ox, oy, ow, oh, "#555", "solid"))
        solid |= new_cells
        placed += 1

    return obstacles, frozenset(solid)


def _overlaps_spawn_zones(ox, oy, ow, oh, map_w, map_h, margin=4) -> bool:
    """Verifica se o obstáculo colide com as zonas de spawn nos 4 cantos."""
    zones = [
        (1, 1, margin + 2, margin + 2),
        (map_w - margin - 3, 1, margin + 2, margin + 2),
        (1, map_h - margin - 3, margin + 2, margin + 2),
        (map_w - margin - 3, map_h - margin - 3, margin + 2, margin + 2),
    ]
    for zx, zy, zw, zh in zones:
        if ox < zx + zw and ox + ow > zx and oy < zy + zh and oy + oh > zy:
            return True
    return False


def spawn_players(
    map_w: int, map_h: int,
    solid: frozenset[tuple[int, int]],
    n_team_a: int = 5,
    n_team_b: int = 5,
) -> tuple[dict[str, tuple], dict[str, str]]:
    """Spawna jogadores em células livres em lados opostos do mapa."""
    positions: dict[str, tuple] = {}
    teams:     dict[str, str]   = {}
    occupied:  set[tuple[int, int]] = set()

    def free(zone_x, zone_y, zone_w, zone_h) -> tuple[int, int]:
        for _ in range(5000):
            x = random.randint(zone_x, zone_x + zone_w - 1)
            y = random.randint(zone_y, zone_y + zone_h - 1)
            if (x, y) not in solid and (x, y) not in occupied:
                return x, y
        raise RuntimeError("Spawn bloqueado — mapa muito denso")

    margin = 6
    # Team A — lado esquerdo
    for i in range(n_team_a):
        pid = f"player_a{i+1}"
        x, y = free(2, 2, margin, map_h - 4)
        positions[pid] = (x, y, 0)
        teams[pid]     = "team_a"
        occupied.add((x, y))

    # Team B — lado direito
    for i in range(n_team_b):
        pid = f"player_b{i+1}"
        x, y = free(map_w - margin - 2, 2, margin, map_h - 4)
        positions[pid] = (x, y, 0)
        teams[pid]     = "team_b"
        occupied.add((x, y))

    return positions, teams
