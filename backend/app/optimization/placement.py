"""Load placement heuristic (Phase 3.5).

Satisfies FR05: given one vehicle's parcels in delivery-visit order, decides
where each parcel physically sits in the cargo bay and in what order it is
loaded, so the load is LIFO-consistent with the delivery order wherever
physical constraints allow it. This is a shelf-stacking *feasibility and
load-ordering heuristic* — it is not a 3D bin-packing contribution, and it
does not claim optimality; the spec is explicit that examiners should read
it as such.

Coordinate convention: `x` (load_position_x) is measured from the cargo
doors (x=0) toward the front/deepest wall (x=cargo_length_cm). Parcels are
processed in *load order* — the reverse of delivery order, so the
last-delivered parcel is loaded first and ends up deepest (large x), and
each subsequently-loaded parcel (which will be delivered earlier) lands
nearer the doors (small x): unloading from the doors then naturally visits
parcels in delivery order. `y` runs across the cargo width, `z` is stack
height. `layer` counts stacked tiers from the floor (0-based).

A vehicle with `has_tail_lift = False` carrying `two_person_lift` parcels
should attract a cost/feasibility penalty upstream (assignment_problem.py) —
this module only decides *where* a parcel goes, not whether the vehicle is
an appropriate choice for it.

Floor packing is First-Fit-Decreasing-Height shelf packing (see
`_band_placement_order`): load-order parcels are grouped into delivery-stop
bands (each band roughly one row's worth of width), and *within* a band,
sorted largest-footprint-first so the row that band opens is sized by its
largest member. This reorders placement *within* a band only — bands
themselves are still visited in load order, so the deepest-first LIFO
relationship *between* bands is untouched.
"""
from dataclasses import dataclass, field
from math import cbrt

from app.core.config import settings


@dataclass
class Placement:
    parcel_id: str
    x: float
    y: float
    z: float
    layer: int
    load_sequence: int  # 1-based; 1 = loaded first = deepest


@dataclass
class PlacementResult:
    placements: dict[str, Placement]
    load_order_exceptions: list[dict] = field(default_factory=list)


@dataclass
class _Column:
    x_start: float  # door-side edge of the row this column belongs to
    footprint_length: float
    footprint_width: float
    y_start: float
    z_top: float = 0.0
    layers: int = 0
    # Remaining weight budget for anything placed *above* this column's
    # current top: the running minimum of (a) what's left of every parcel
    # already in the stack's own `max_stack_weight_kg`, each reduced by the
    # weight of everything placed above it, and (b) nothing shortcuts to
    # just the topmost parcel's limit, or a heavy parcel could sit on a
    # stack whose bottom parcel tolerates far less (constraint 7).
    stack_headroom_kg: float = 0.0
    open_for_stacking: bool = True


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
    last-resort fallback — by the time parcels reach here, Phase 1's
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


def _orientations(parcel, length: float, width: float) -> list[tuple[float, float]]:
    """Floor-rotation candidates (length, width). `do_not_tilt` and
    `loading_orientation_fixed` both forbid changing which face is up, but a
    box may still be yawed 90 degrees on the floor unless the orientation is
    explicitly fixed."""
    if parcel.loading_orientation_fixed or length == width:
        return [(length, width)]
    return [(length, width), (width, length)]


def _fits_bay_at_all(parcel, vehicle) -> bool:
    length, width, height = _footprint(parcel)
    if height > vehicle.cargo_height_cm:
        return False
    return any(
        l <= vehicle.cargo_length_cm and w <= vehicle.cargo_width_cm
        for l, w in _orientations(parcel, length, width)
    )


def _try_stack(parcel, weight: float, height: float, columns: list[_Column], vehicle) -> _Column | None:
    """First open column this parcel can be stacked on top of, honouring
    fragility/stackability, remaining stack-weight budget, layer cap and
    cargo height. Tried before opening new floor space."""
    length, width, _ = _footprint(parcel)
    for column in columns:
        if not column.open_for_stacking:
            continue
        if column.layers >= vehicle.max_stack_layers:
            continue
        if column.z_top + height > vehicle.cargo_height_cm:
            continue
        if weight > column.stack_headroom_kg:
            continue
        for l, w in _orientations(parcel, length, width):
            if l <= column.footprint_length and w <= column.footprint_width:
                return column
    return None


def _footprint_length(parcel) -> float:
    """The longer of a parcel's two floor-orientation sides — used only to
    order parcels within a band (see `_band_placement_order`), so the
    largest parcel in a band is the one that opens (and therefore sizes)
    the row."""
    length, width, _height = _footprint(parcel)
    return max(length, width)


def _band_placement_order(parcels_in_delivery_order: list, load_order: list[int], vehicle) -> list[int]:
    """Partitions `load_order` into delivery-stop bands — a band is a
    maximal run of load-order parcels whose combined (conservative) width
    fills roughly one row — then sorts *within* each band by descending
    footprint length before concatenating the bands back together.

    Bands are still visited in load order, so band 0 is placed deepest and
    later bands land progressively nearer the doors: LIFO is preserved
    *between* bands. Sorting within a band does not disturb that, since
    sibling items in a band all land in the same depth-slice regardless of
    which order they're placed in — it only changes which of them opens the
    row (the largest, so no smaller band-mate is later forced into a
    premature new row)."""
    bands: list[list[int]] = []
    current: list[int] = []
    current_width = 0.0
    for idx in load_order:
        parcel = parcels_in_delivery_order[idx]
        length, width, _height = _footprint(parcel)
        narrowest = min(w for _l, w in _orientations(parcel, length, width))
        if current and current_width + narrowest > vehicle.cargo_width_cm:
            bands.append(current)
            current, current_width = [], 0.0
        current.append(idx)
        current_width += narrowest
    if current:
        bands.append(current)

    order: list[int] = []
    for band in bands:
        order.extend(sorted(band, key=lambda i: -_footprint_length(parcels_in_delivery_order[i])))
    return order


def _place_in_open_rows(parcel, rows: list[_Row], vehicle) -> _Column | None:
    """Tries every row opened so far — not just the most recent one — before
    the caller falls back to opening a new one, so leftover width in an
    earlier row is reused instead of abandoned."""
    length, width, _height = _footprint(parcel)
    for row in rows:
        for l, w in _orientations(parcel, length, width):
            if l <= row.depth + 1e-9 and row.y_used + w <= vehicle.cargo_width_cm + 1e-9:
                column = _Column(x_start=row.x_start, footprint_length=l, footprint_width=w, y_start=row.y_used)
                row.y_used += w
                return column
    return None


def _open_new_row(parcel, rows: list[_Row], vehicle, next_x_start: float) -> tuple[_Column | None, float]:
    """Opens a fresh row one step nearer the doors. Only called once no
    already-open row has width to spare for this parcel (see
    `_place_in_open_rows`) — a new row is never opened merely because a
    parcel is longer than the *current* row, since every open row is tried
    first."""
    length, width, _height = _footprint(parcel)
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
        return column, new_x_start
    return None, next_x_start


def _lifo_exceptions(parcels_in_delivery_order: list, placements: dict[str, Placement]) -> list[dict]:
    """O(n) LIFO-violation scan: a delivery-order walk tracking the maximum
    `x` seen so far. Any parcel whose `x` is less than that running maximum
    is nearer the doors than something delivered *before* it — i.e. it will
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


def attempt_placement(
    parcels_in_delivery_order: list, vehicle, *, collect_exceptions: bool = True
) -> PlacementResult | None:
    """Places every parcel for one vehicle. Returns `None` if any parcel
    cannot be placed at all (too big for the bay in any orientation, or the
    bay is full) — the caller (the NSGA-II stacking constraint, Phase 3.2
    #7) treats that as an infeasible solution.

    `collect_exceptions=False` skips the LIFO-violation diagnostics (see
    `_lifo_exceptions`) entirely — pass it from the GA's constraint
    evaluation, which only needs the None/not-None feasibility verdict and
    never reads the exception list. Collect them once, at persistence time,
    for the solution actually selected."""
    n = len(parcels_in_delivery_order)
    if n == 0:
        return PlacementResult(placements={})

    for parcel in parcels_in_delivery_order:
        if not _fits_bay_at_all(parcel, vehicle):
            return None

    load_order = list(range(n - 1, -1, -1))  # last-delivered first
    placement_order = _band_placement_order(parcels_in_delivery_order, load_order, vehicle)

    columns: list[_Column] = []
    rows: list[_Row] = []
    next_x_start = vehicle.cargo_length_cm
    placements: dict[str, Placement] = {}

    for load_sequence, idx in enumerate(placement_order, start=1):
        parcel = parcels_in_delivery_order[idx]
        weight = parcel.weight_kg
        _length, _width, height = _footprint(parcel)

        column = _try_stack(parcel, weight, height, columns, vehicle)
        max_stack_weight = parcel.max_stack_weight_kg if parcel.max_stack_weight_kg is not None else 0.0
        if column is None:
            column = _place_in_open_rows(parcel, rows, vehicle)
            if column is None:
                column, next_x_start = _open_new_row(parcel, rows, vehicle, next_x_start)
            if column is None:
                return None
            columns.append(column)
            z, layer = 0.0, 0
            # Floor parcel: headroom for everything above it starts at its
            # own budget — nothing has been placed above it yet.
            column.stack_headroom_kg = max_stack_weight
        else:
            z, layer = column.z_top, column.layers
            # Accumulated-weight-above check (constraint 7): the budget for
            # anything placed above *this* parcel is the tighter of what's
            # left of the stack's existing headroom (after this parcel's
            # own weight) and this parcel's own limit — not just this
            # parcel's limit on its own, which would ignore every parcel
            # already below it.
            column.stack_headroom_kg = min(column.stack_headroom_kg - weight, max_stack_weight)

        column.z_top = z + height
        column.layers = layer + 1
        # A fragile or non-stackable parcel must be the top of its column
        # from here on; everything else may still take more weight up to
        # the accumulated headroom computed above.
        stackable = parcel.stackable if parcel.stackable is not None else True
        fragile = bool(parcel.fragile)
        column.open_for_stacking = stackable and not fragile

        placements[parcel.parcel_id] = Placement(
            parcel_id=parcel.parcel_id, x=column.x_start, y=column.y_start, z=z, layer=layer,
            load_sequence=load_sequence,
        )

    exceptions = _lifo_exceptions(parcels_in_delivery_order, placements) if collect_exceptions else []
    return PlacementResult(placements=placements, load_order_exceptions=exceptions)
