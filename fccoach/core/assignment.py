"""Affectation optimale (algorithme hongrois), sans dépendance externe.

Utilisée par le suivi (détections <-> tracks) et l'estimation de formation
(joueurs <-> postes du gabarit). Matrices rectangulaires acceptées.
"""

from __future__ import annotations

import numpy as np


def linear_sum_assignment(cost: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Équivalent minimal de scipy.optimize.linear_sum_assignment (minimisation)."""
    cost = np.asarray(cost, dtype=float)
    if cost.size == 0:
        return np.zeros(0, int), np.zeros(0, int)
    transposed = cost.shape[0] > cost.shape[1]
    c = cost.T if transposed else cost
    n, m = c.shape  # n <= m
    INF = float("inf")
    u = np.zeros(n + 1)
    v = np.zeros(m + 1)
    p = np.zeros(m + 1, dtype=int)     # p[j] = ligne affectée à la colonne j (1-indexé)
    way = np.zeros(m + 1, dtype=int)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = np.full(m + 1, INF)
        used = np.zeros(m + 1, dtype=bool)
        while True:
            used[j0] = True
            i0 = p[j0]
            cur = c[i0 - 1] - u[i0] - v[1:]
            free = ~used[1:]
            better = free & (cur < minv[1:])
            minv[1:][better] = cur[better]
            way[1:][better] = j0
            cand = np.where(free, minv[1:], INF)
            j1 = int(np.argmin(cand)) + 1
            delta = cand[j1 - 1]
            u[p[used]] += delta
            v[used] -= delta
            minv[1:][free] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break
    rows, cols = [], []
    for j in range(1, m + 1):
        if p[j]:
            rows.append(p[j] - 1)
            cols.append(j - 1)
    r, k = np.array(rows, int), np.array(cols, int)
    if transposed:
        r, k = k, r
    order = np.argsort(r)
    return r[order], k[order]
