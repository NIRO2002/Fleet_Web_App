"""Solution selection from the NSGA-II Pareto front, and hypervolume
(Phase 3.6/3.7).

Satisfies FR04/SO4: the API always returns the *whole* front — this module
only picks the single solution that gets persisted as the plan's
`VirtualVehicle` rows. A scalar score may exist *only* here, as an optional
post-hoc tie-breaker among already non-dominated solutions — never inside
the optimizer's own objectives (see `assignment_problem.py`).
"""
import numpy as np
from pymoo.indicators.hv import HV


def pareto_front(res) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """`(F, X, G)` restricted to feasible solutions if any exist. Falls back
    to the full (possibly infeasible) result set so the caller can report
    infeasibility explicitly rather than an empty front silently standing
    in for "nothing worked"."""
    if res.F is None or res.X is None:
        raise ValueError("NSGA-II produced no result.")
    F, X, G = res.F, res.X, res.G
    if G is not None:
        feasible = np.all(G <= 1e-6, axis=1)
        if feasible.any():
            return F[feasible], X[feasible], G[feasible]
    return F, X, G


def knee_point_index(F: np.ndarray) -> int:
    """Normalises every objective to [0,1] using the front's own ideal
    (min) and nadir (max) points, then returns the index of the solution
    closest (Euclidean) to the ideal point — the default single-solution
    pick (spec 3.6)."""
    ideal = F.min(axis=0)
    nadir = F.max(axis=0)
    span = np.where(nadir - ideal > 1e-12, nadir - ideal, 1.0)
    normalized = (F - ideal) / span
    distances = np.linalg.norm(normalized, axis=1)
    return int(np.argmin(distances))


def preference_weighted_index(F: np.ndarray, weights: list[float]) -> int:
    """Picks among an already non-dominated front by a caller-supplied
    preference vector (planner-driven decision support) — this is applied
    only here, never as the optimizer's own objective."""
    if len(weights) != F.shape[1]:
        raise ValueError(f"preference_weights must have {F.shape[1]} entries, got {len(weights)}")
    ideal = F.min(axis=0)
    nadir = F.max(axis=0)
    span = np.where(nadir - ideal > 1e-12, nadir - ideal, 1.0)
    normalized = (F - ideal) / span
    scores = normalized @ np.asarray(weights, dtype=float)
    return int(np.argmin(scores))


def select_solution(res, preference_weights: list[float] | None = None):
    """Returns `(index, F, X, G)` for the chosen solution's position within
    the (feasibility-filtered) front."""
    F, X, G = pareto_front(res)
    idx = preference_weighted_index(F, preference_weights) if preference_weights is not None else knee_point_index(F)
    return idx, F, X, G


def hypervolume(F: np.ndarray, reference_point: np.ndarray | None = None) -> float:
    """Hypervolume of the (minimised) front. The reference point is the
    worst value observed per objective *in this instance's own front*, with
    a 5% margin — documented and instance-specific, so hypervolumes are
    only compared across runs that used the same reference-point rule, not
    treated as universally comparable absolute numbers."""
    if F.shape[0] == 0:
        return 0.0
    if reference_point is None:
        reference_point = F.max(axis=0) * 1.05 + 1e-6
    indicator = HV(ref_point=reference_point)
    return float(indicator(F))
