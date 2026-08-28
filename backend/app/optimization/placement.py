"""Load placement heuristic (Phase 3.5).

Satisfies FR05: given one vehicle's parcels in delivery-visit order, decides
where each parcel physically sits in the cargo bay and in what order it is
loaded, so the load is LIFO-consistent with the delivery order wherever
physical constraints allow it. This is a shelf-stacking *feasibility and
load-ordering heuristic* - it is not a 3D bin-packing contribution, and it
does not claim optimality; the spec is explicit that examiners should read
it as such.

Coordinate convention: `x` (load_position_x) is measured from the cargo
doors (x=0) toward the front/deepest wall (x=cargo_length_cm); `y` runs
across cargo width and `z` is height. Packing order is only a geometry
heuristic. Final `load_sequence` comes from hard insertion-accessibility and
stack-support precedence, with reverse delivery order as its deterministic
LIFO tie-breaker. `layer` counts stacked tiers from the floor (0-based).

A vehicle with `has_tail_lift = False` carrying `two_person_lift` parcels
should attract a cost/feasibility penalty upstream (assignment_problem.py) -
this module only decides *where* a parcel goes, not whether the vehicle is
an appropriate choice for it.

Floor/stack packing is First-Fit-Decreasing-Height shelf packing with a
stackability-aware placement order (see `_placement_order`, Fix Pass 4 S1):
parcels able to be stacked on (`stackable and not fragile`) are placed
before parcels that cannot (fragile or non-stackable), and within each of
those two groups, largest-footprint-area-first. This replaces an earlier
row-width-sized "band" grouping that, on real (non-uniform-size) parcel
data, capped effective capacity at roughly one floor's worth regardless of
`max_stack_layers` -- see `docs/FIX_PASS_4_REPORT.md` for the diagnosis and
the verified fix. Placing stackable parcels first lets them build up tall
columns before any parcel that would permanently close a column (a fragile
or non-stackable parcel can be supported, but cannot support anything
placed after it) gets a chance to cap one prematurely. This reorders
placement globally within a vehicle, not within any narrower grouping - the
existing LIFO-exception audit (`_lifo_exceptions`) is what records where the
physical result deviates from pure delivery order, rather than the ordering
enforcing strict delivery order during packing itself; that is unchanged
from before this pass.

LIFO banding governs depth from the doors; weight ordering governs only
which open column may receive a parcel. When those goals conflict, LIFO
depth wins and `_lifo_exceptions` records any physical compromise. Fragile
and non-stackable parcels may be placed on a compatible support, but close
that column and can never support another parcel.
"""
from dataclasses import dataclass, field
import heapq
from math import cbrt

from app.core.config import settings

STACK_WEIGHT_TOLERANCE_KG = settings.stack_weight_tolerance_kg


@dataclass
class Placement:
    parcel_id: str
    x: float
    y: float
    z: float
    layer: int
    load_sequence: int  # 1-based; assigned by physical precedence
    placed_length_cm: float
    placed_width_cm: float
    placed_height_cm: float


@dataclass
class PlacementResult:
    placements: dict[str, Placement]
    load_order_exceptions: list[dict] = field(default_factory=list)
    loading_precedence: list[dict] = field(default_factory=list)
    support_by_parcel: dict[str, str] = field(default_factory=dict)
    physical_load_order_valid: bool = True


@dataclass
class _Column:
    x_start: float  # door-side edge of the row this column belongs to
    footprint_length: float
    footprint_width: float
    y_start: float
    z_top: float = 0.0
    layers: int = 0
    top_weight_kg: float = 0.0
    open_for_stacking: bool = True
    top_parcel_id: str | None = None


@dataclass
class _PlacementCandidate:
    column: _Column
    length: float
    width: float


@dataclass
class _VehicleStackState:
    """Running total of weight stacked above the bay floor (layer > 0),
    across every column in the vehicle. The catalog's field-data-backed
    `vehicle_max_stack_weight_kg` bounds this total independently."""

    cumulative_above_floor_kg: float = 0.0


@dataclass
class _Row:
    """One depth-slice of the cargo bay, spanning the full width. `depth` is
    fixed by whichever parcel opened the row (see `_open_new_row`) and never
    changes; `y_used` tracks how much of the row's width has been claimed so
    far, so later, narrower parcels can still land in an already-open row
    instead of forcing a fresh one."""

    x_start: float
    depth: float
    y_used: float = 0.0


def _footprint(parcel) -> tuple[float, float, float]:
    """(length, width, height) in cm, imputing a cube from volume as a
    last-resort fallback - by the time parcels reach here, Phase 1's
    importer should already have populated real dimensions. Whenever the
    dimensions are imputed (flagged by the importer via
    `dimensions_imputed`, or imputed here directly), a safety factor
    inflates the imputed side (F12), so an unreliable cube claims more
    floor/stack space than it might actually need rather than less."""
    length, width, height = parcel.length_cm, parcel.width_cm, parcel.height_cm
    if length and width and height:
        if getattr(parcel, "dimensions_imputed", False):
            factor = settings.imputed_dimension_safety_factor
            return float(length) * factor, float(width) * factor, float(height) * factor
        return float(length), float(width), float(height)
    side = cbrt(max(parcel.volume_m3, 1e-9) * 1_000_000) * settings.imputed_dimension_safety_factor
    return side, side, side


def _get_footprint(parcel, footprint_cache: dict | None) -> tuple[float, float, float]:
    """Same as `_footprint`, but memoized per `id(parcel)` when a cache dict
    is supplied. Profiling a full GA run showed a single parcel's footprint
    recomputed up to ~5 times per `attempt_placement` call (once each from
    `_fits_bay_at_all`, `_placement_order`, `attempt_placement` itself,
    `_try_stack`, and whichever of `_place_in_open_rows`/`_open_new_row` is
    tried) -- `_footprint` is pure given a parcel, so this is wasted
    recomputation, not a correctness requirement. Scoped to one
    `attempt_placement` call (never module-level), so it can't leak state
    across calls or problem instances."""
    if footprint_cache is None:
        return _footprint(parcel)
    key = id(parcel)
    cached = footprint_cache.get(key)
    if cached is None:
        cached = _footprint(parcel)
        footprint_cache[key] = cached
    return cached


def _orientations(parcel, length: float, width: float) -> list[tuple[float, float]]:
    """Floor-rotation candidates (length, width). `do_not_tilt` and
    `loading_orientation_fixed` both forbid changing which face is up, but a
    box may still be yawed 90 degrees on the floor unless the orientation is
    explicitly fixed."""
    if parcel.loading_orientation_fixed or length == width:
        return [(length, width)]
    return [(length, width), (width, length)]


def _fits_bay_at_all(parcel, vehicle, footprint_cache: dict | None = None) -> bool:
    length, width, height = _get_footprint(parcel, footprint_cache)
    if height > vehicle.cargo_height_cm:
        return False
    return any(
        l <= vehicle.cargo_length_cm and w <= vehicle.cargo_width_cm
        for l, w in _orientations(parcel, length, width)
    )


def _try_stack(
    parcel, weight: float, height: float, columns: list[_Column], vehicle, stack_state: _VehicleStackState,
    footprint_cache: dict | None = None, *, enforce_weight_order: bool = True,
) -> _PlacementCandidate | None:
    """Best compatible open column for stacking.

    The incoming parcel must be no heavier than the current top within
    ``STACK_WEIGHT_TOLERANCE_KG``. Fragile/non-stackable incoming parcels
    remain valid placement targets and close the column after placement.
    Footprint, layer, height and vehicle-level above-floor weight limits
    are enforced unchanged.
    """
    length, width, _ = _get_footprint(parcel, footprint_cache)
    vehicle_max_stack_weight = getattr(vehicle, "vehicle_max_stack_weight_kg", None)
    # Choose the heaviest compatible top. This integrates weight ordering
    # into column selection without globally reordering the parcel stream.
    for column in sorted(columns, key=lambda c: c.top_weight_kg, reverse=True):
        if not column.open_for_stacking:
            continue
        if column.layers >= vehicle.max_stack_layers:
            continue
        if column.z_top + height > vehicle.cargo_height_cm:
            continue
        if enforce_weight_order and weight > column.top_weight_kg + STACK_WEIGHT_TOLERANCE_KG:
            continue
        if (
            vehicle_max_stack_weight is not None
            and stack_state.cumulative_above_floor_kg + weight > vehicle_max_stack_weight
        ):
            continue
        for l, w in _orientations(parcel, length, width):
            if l <= column.footprint_length and w <= column.footprint_width:
                return _PlacementCandidate(column=column, length=l, width=w)
    return None


def _footprint_area(parcel, footprint_cache: dict | None = None) -> float:
    length, width, _height = _get_footprint(parcel, footprint_cache)
    return length * width


def _blocks_stacking(parcel) -> bool:
    """True if this parcel, once placed, closes its column to anything
    placed after it (`column.open_for_stacking = stackable and not
    fragile`, unchanged below) -- i.e. a fragile or non-stackable parcel."""
    stackable = parcel.stackable if parcel.stackable is not None else True
    return (not stackable) or bool(parcel.fragile)


def _placement_order(
    parcels_in_delivery_order: list, load_order: list[int], vehicle, footprint_cache: dict | None = None
) -> list[int]:
    """Fix Pass 4 S1: parcels that can be stacked on (`stackable and not
    fragile`) are placed before parcels that cannot -- within each group,
    largest footprint area first.

    Replaces the earlier row-width-sized "band" grouping (see
    `docs/FIX_PASS_4_REPORT.md` for the diagnosis): sizing groups to one
    row's width meant a new group's largest member routinely didn't fit any
    column opened by an earlier, differently-sized group, so it opened a
    fresh floor column instead of stacking -- collapsing effective capacity
    to roughly one floor's worth regardless of `max_stack_layers`.

    Placing all stack-eligible parcels first, largest-area first, lets them
    build up tall columns via the existing `_try_stack`-first logic in
    `attempt_placement` before any column-closing (fragile/non-stackable)
    parcel gets a turn to cap one prematurely. This is a global reordering
    within the vehicle, not a narrower per-group one -- LIFO is not
    strictly preserved by construction (as it wasn't under band grouping
    either); `_lifo_exceptions` records where the physical result deviates
    from delivery order."""
    stack_eligible = [i for i in load_order if not _blocks_stacking(parcels_in_delivery_order[i])]
    blocked = [i for i in load_order if _blocks_stacking(parcels_in_delivery_order[i])]

    def by_area_desc(idx: int) -> float:
        return -_footprint_area(parcels_in_delivery_order[idx], footprint_cache)

    stack_eligible.sort(key=by_area_desc)
    blocked.sort(key=by_area_desc)
    return stack_eligible + blocked


def _place_in_open_rows(parcel, rows: list[_Row], vehicle, footprint_cache: dict | None = None) -> _PlacementCandidate | None:
    """Tries every row opened so far - not just the most recent one - before
    the caller falls back to opening a new one, so leftover width in an
    earlier row is reused instead of abandoned."""
    length, width, _height = _get_footprint(parcel, footprint_cache)
    for row in rows:
        for l, w in _orientations(parcel, length, width):
            if l <= row.depth + 1e-9 and row.y_used + w <= vehicle.cargo_width_cm + 1e-9:
                column = _Column(x_start=row.x_start, footprint_length=l, footprint_width=w, y_start=row.y_used)
                row.y_used += w
                return _PlacementCandidate(column=column, length=l, width=w)
    return None


def _open_new_row(
    parcel, rows: list[_Row], vehicle, next_x_start: float, footprint_cache: dict | None = None
) -> tuple[_PlacementCandidate | None, float]:
    """Opens a fresh row one step nearer the doors. Only called once no
    already-open row has width to spare for this parcel (see
    `_place_in_open_rows`) - a new row is never opened merely because a
    parcel is longer than the *current* row, since every open row is tried
    first."""
    length, width, _height = _get_footprint(parcel, footprint_cache)
    # Prefer presenting the longer side as depth, so this row is as deep as
    # this parcel needs and can still absorb shorter band-mates later.
    for l, w in sorted(_orientations(parcel, length, width), key=lambda lw: -lw[0]):
        if w > vehicle.cargo_width_cm + 1e-9:
            continue
        new_x_start = next_x_start - l
        if new_x_start < -1e-9:
            continue
        rows.append(_Row(x_start=new_x_start, depth=l, y_used=w))
        column = _Column(x_start=new_x_start, footprint_length=l, footprint_width=w, y_start=0.0)
        return _PlacementCandidate(column=column, length=l, width=w), new_x_start
    return None, next_x_start


def _lifo_exceptions(parcels_in_delivery_order: list, placements: dict[str, Placement]) -> list[dict]:
    """O(n) LIFO-violation scan: a delivery-order walk tracking the maximum
    `x` seen so far. Any parcel whose `x` is less than that running maximum
    is nearer the doors than something delivered *before* it - i.e. it will
    have to be dug out past an earlier stop's parcel, one exception per
    such parcel. Replaces an O(n^2) all-pairs scan that, at 400 parcels, ran
    80,000 comparisons per slot/individual/generation to produce a list the
    GA itself never reads (see `collect_exceptions`)."""
    exceptions = []
    running_max_x = float("-inf")
    max_x_parcel_id = None
    for parcel in parcels_in_delivery_order:
        x = placements[parcel.parcel_id].x
        if x < running_max_x:
            exceptions.append(
                {
                    "parcel_a": max_x_parcel_id,
                    "parcel_b": parcel.parcel_id,
                    "reason": (
                        "Physical stacking/dimensional constraints forced a load "
                        "position that is not strictly LIFO relative to the delivery order."
                    ),
                }
            )
        else:
            running_max_x = x
            max_x_parcel_id = parcel.parcel_id
    return exceptions


GEOMETRY_TOLERANCE_CM = 1e-7


def _intervals_overlap(a0: float, a1: float, b0: float, b1: float, tolerance: float = GEOMETRY_TOLERANCE_CM) -> bool:
    """Strict interval overlap; touching faces are not collisions/blockers."""
    return min(a1, b1) - max(a0, b0) > tolerance


def _aabb_overlap(a: Placement, b: Placement, tolerance: float = GEOMETRY_TOLERANCE_CM) -> bool:
    return (
        _intervals_overlap(a.x, a.x + a.placed_length_cm, b.x, b.x + b.placed_length_cm, tolerance)
        and _intervals_overlap(a.y, a.y + a.placed_width_cm, b.y, b.y + b.placed_width_cm, tolerance)
        and _intervals_overlap(a.z, a.z + a.placed_height_cm, b.z, b.z + b.placed_height_cm, tolerance)
    )


def _insertion_path_blocked(target: Placement, blocker: Placement, tolerance: float = GEOMETRY_TOLERANCE_CM) -> bool:
    """Whether ``blocker`` intersects the target's straight +x swept corridor.

    The parcel translates from the door at x=0 without rotating or changing
    y/z. Only an already-loaded parcel whose door-side edge is before the
    target and whose y and z envelopes overlap can obstruct that motion.
    """
    return (
        blocker.x < target.x - tolerance
        and _intervals_overlap(
            target.y, target.y + target.placed_width_cm,
            blocker.y, blocker.y + blocker.placed_width_cm, tolerance,
        )
        and _intervals_overlap(
            target.z, target.z + target.placed_height_cm,
            blocker.z, blocker.z + blocker.placed_height_cm, tolerance,
        )
    )


def _is_reachable_from_door(target: Placement, loaded: list[Placement]) -> bool:
    return not any(_insertion_path_blocked(target, blocker) for blocker in loaded)


def _physical_precedence(
    placements: dict[str, Placement], support_by_parcel: dict[str, str]
) -> tuple[dict[str, set[str]], list[dict]]:
    """Build hard accessibility and direct stack-support precedence edges."""
    successors = {parcel_id: set() for parcel_id in placements}
    diagnostics: list[dict] = []
    values = list(placements.values())
    for deep in values:
        for near in values:
            if deep.parcel_id == near.parcel_id or not _insertion_path_blocked(deep, near):
                continue
            if near.parcel_id not in successors[deep.parcel_id]:
                successors[deep.parcel_id].add(near.parcel_id)
                diagnostics.append({
                    "before": deep.parcel_id, "after": near.parcel_id,
                    "reason": "accessibility",
                    "detail": f"{near.parcel_id} blocks {deep.parcel_id}'s rear-door insertion corridor.",
                })
    for top_id, base_id in support_by_parcel.items():
        if top_id not in placements or base_id not in placements:
            continue
        if top_id not in successors[base_id]:
            successors[base_id].add(top_id)
            diagnostics.append({
                "before": base_id, "after": top_id, "reason": "stack_support",
                "detail": f"{base_id} must be loaded before supported parcel {top_id}.",
            })
    return successors, diagnostics


def _assign_physical_load_sequence(
    parcels_in_delivery_order: list, placements: dict[str, Placement], support_by_parcel: dict[str, str]
) -> list[dict] | None:
    successors, diagnostics = _physical_precedence(placements, support_by_parcel)
    indegree = {parcel_id: 0 for parcel_id in placements}
    for after_ids in successors.values():
        for after_id in after_ids:
            indegree[after_id] += 1
    lifo_rank = {
        parcel.parcel_id: rank
        for rank, parcel in enumerate(reversed(parcels_in_delivery_order))
    }
    eligible = [(lifo_rank[parcel_id], parcel_id) for parcel_id, degree in indegree.items() if degree == 0]
    heapq.heapify(eligible)
    ordered: list[str] = []
    while eligible:
        _rank, parcel_id = heapq.heappop(eligible)
        ordered.append(parcel_id)
        for after_id in sorted(successors[parcel_id]):
            indegree[after_id] -= 1
            if indegree[after_id] == 0:
                heapq.heappush(eligible, (lifo_rank[after_id], after_id))
    if len(ordered) != len(placements):
        return None
    for sequence, parcel_id in enumerate(ordered, start=1):
        placements[parcel_id].load_sequence = sequence
    return diagnostics


def validate_loading_sequence(parcels, vehicle, result: PlacementResult) -> bool:
    """Validate bounds, collision, support, reachability, and 1..N sequence."""
    placements = result.placements
    if set(placements) != {p.parcel_id for p in parcels}:
        return False
    ordered = sorted(placements.values(), key=lambda p: p.load_sequence)
    if [p.load_sequence for p in ordered] != list(range(1, len(ordered) + 1)):
        return False
    for placement in ordered:
        if min(placement.x, placement.y, placement.z) < -GEOMETRY_TOLERANCE_CM:
            return False
        if placement.x + placement.placed_length_cm > vehicle.cargo_length_cm + GEOMETRY_TOLERANCE_CM:
            return False
        if placement.y + placement.placed_width_cm > vehicle.cargo_width_cm + GEOMETRY_TOLERANCE_CM:
            return False
        if placement.z + placement.placed_height_cm > vehicle.cargo_height_cm + GEOMETRY_TOLERANCE_CM:
            return False
    for index, placement in enumerate(ordered):
        if any(_aabb_overlap(placement, other) for other in ordered[index + 1:]):
            return False
    loaded: list[Placement] = []
    loaded_ids: set[str] = set()
    for placement in ordered:
        support_id = result.support_by_parcel.get(placement.parcel_id)
        if support_id is not None and support_id not in loaded_ids:
            return False
        if not _is_reachable_from_door(placement, loaded):
            return False
        loaded.append(placement)
        loaded_ids.add(placement.parcel_id)
    return True


def attempt_placement(
    parcels_in_delivery_order: list, vehicle, *, collect_exceptions: bool = True,
    enforce_weight_order: bool = settings.enforce_weight_order,
) -> PlacementResult | None:
    """Places every parcel for one vehicle. Returns `None` if any parcel
    cannot be placed at all (too big for the bay in any orientation, or the
    bay is full) - the caller (the NSGA-II stacking constraint, Phase 3.2
    #7) treats that as an infeasible solution.

    `collect_exceptions=False` skips the LIFO-violation diagnostics (see
    `_lifo_exceptions`) entirely - pass it from the GA's constraint
    evaluation, which only needs the None/not-None feasibility verdict and
    never reads the exception list. Collect them once, at persistence time,
    for the solution actually selected."""
    n = len(parcels_in_delivery_order)
    if n == 0:
        return PlacementResult(placements={})

    # Scoped to this call only (never module-level -- see _get_footprint):
    # a parcel's footprint is read repeatedly across this function and its
    # helpers, and is pure given the parcel, so compute it once per parcel
    # per call instead of up to ~5 times.
    footprint_cache: dict = {}

    for parcel in parcels_in_delivery_order:
        if not _fits_bay_at_all(parcel, vehicle, footprint_cache):
            return None

    load_order = list(range(n - 1, -1, -1))  # last-delivered first
    preferred_order = _placement_order(parcels_in_delivery_order, load_order, vehicle, footprint_cache)

    def pack(placement_order: list[int]) -> PlacementResult | None:
        columns: list[_Column] = []
        rows: list[_Row] = []
        next_x_start = vehicle.cargo_length_cm
        placements: dict[str, Placement] = {}
        support_by_parcel: dict[str, str] = {}
        stack_state = _VehicleStackState()

        for idx in placement_order:
            parcel = parcels_in_delivery_order[idx]
            weight = parcel.weight_kg
            _length, _width, height = _get_footprint(parcel, footprint_cache)

            candidate = _try_stack(
                parcel, weight, height, columns, vehicle, stack_state, footprint_cache,
                enforce_weight_order=enforce_weight_order,
            )
            if candidate is None:
                candidate = _place_in_open_rows(parcel, rows, vehicle, footprint_cache)
                if candidate is None:
                    candidate, next_x_start = _open_new_row(
                        parcel, rows, vehicle, next_x_start, footprint_cache
                    )
                if candidate is None:
                    return None
                columns.append(candidate.column)
                z, layer = 0.0, 0
            else:
                z, layer = candidate.column.z_top, candidate.column.layers
                if candidate.column.top_parcel_id is None:
                    return None
                support_by_parcel[parcel.parcel_id] = candidate.column.top_parcel_id
                stack_state.cumulative_above_floor_kg += weight

            column = candidate.column
            column.z_top = z + height
            column.layers = layer + 1
            column.top_weight_kg = weight
            column.top_parcel_id = parcel.parcel_id
            stackable = parcel.stackable if parcel.stackable is not None else True
            column.open_for_stacking = stackable and not bool(parcel.fragile)

            placements[parcel.parcel_id] = Placement(
                parcel_id=parcel.parcel_id, x=column.x_start, y=column.y_start, z=z, layer=layer,
                load_sequence=0, placed_length_cm=candidate.length,
                placed_width_cm=candidate.width, placed_height_cm=height,
            )

        precedence = _assign_physical_load_sequence(
            parcels_in_delivery_order, placements, support_by_parcel
        )
        if precedence is None:
            return None
        result = PlacementResult(
            placements=placements,
            loading_precedence=precedence if collect_exceptions else [],
            support_by_parcel=support_by_parcel,
        )
        if not validate_loading_sequence(parcels_in_delivery_order, vehicle, result):
            return None
        result.load_order_exceptions = (
            _lifo_exceptions(parcels_in_delivery_order, placements) if collect_exceptions else []
        )
        return result

    result = pack(preferred_order)
    if result is None and preferred_order != load_order:
        # Deterministic repair: retry packing in pure reverse-delivery order.
        # If its completed precedence graph is also cyclic/unreachable, the
        # assignment is physically infeasible and must not enter a plan.
        result = pack(load_order)
    return result
