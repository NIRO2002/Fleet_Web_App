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
"""
from dataclasses import dataclass, field
from math import cbrt


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
    top_weight_limit: float = 0.0
    open_for_stacking: bool = True


def _footprint(parcel) -> tuple[float, float, float]:
    """(length, width, height) in cm, imputing a cube from volume as a
    last-resort fallback — by the time parcels reach here, Phase 1's
    importer should already have populated real dimensions."""
    length, width, height = parcel.length_cm, parcel.width_cm, parcel.height_cm
    if length and width and height:
        return float(length), float(width), float(height)
    side = cbrt(max(parcel.volume_m3, 1e-9) * 1_000_000)
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
        if weight > column.top_weight_limit:
            continue
        for l, w in _orientations(parcel, length, width):
            if l <= column.footprint_length and w <= column.footprint_width:
                return column
    return None


def _open_new_column(parcel, columns: list[_Column], row_state: dict, vehicle) -> _Column | None:
    length, width, _ = _footprint(parcel)

    # Try the row currently being filled first.
    for l, w in _orientations(parcel, length, width):
        if l <= row_state["depth"] and row_state["y_used"] + w <= vehicle.cargo_width_cm:
            column = _Column(x_start=row_state["x_start"], footprint_length=l, footprint_width=w, y_start=row_state["y_used"])
            row_state["y_used"] += w
            columns.append(column)
            return column

    # Doesn't fit the current row — open a new one, one step nearer the doors.
    for l, w in _orientations(parcel, length, width):
        if w > vehicle.cargo_width_cm:
            continue
        new_x_start = row_state["x_start"] - l
        if new_x_start < -1e-9:
            continue
        row_state["x_start"] = new_x_start
        row_state["depth"] = l
        row_state["y_used"] = w
        column = _Column(x_start=new_x_start, footprint_length=l, footprint_width=w, y_start=0.0)
        columns.append(column)
        return column

    return None


def attempt_placement(parcels_in_delivery_order: list, vehicle) -> PlacementResult | None:
    """Places every parcel for one vehicle. Returns `None` if any parcel
    cannot be placed at all (too big for the bay in any orientation, or the
    bay is full) — the caller (the NSGA-II stacking constraint, Phase 3.2
    #7) treats that as an infeasible solution."""
    n = len(parcels_in_delivery_order)
    if n == 0:
        return PlacementResult(placements={})

    for parcel in parcels_in_delivery_order:
        if not _fits_bay_at_all(parcel, vehicle):
            return None

    load_order = list(range(n - 1, -1, -1))  # last-delivered first
    columns: list[_Column] = []
    row_state = {"x_start": vehicle.cargo_length_cm, "depth": 0.0, "y_used": vehicle.cargo_width_cm}
    placements: dict[str, Placement] = {}

    for load_sequence, idx in enumerate(load_order, start=1):
        parcel = parcels_in_delivery_order[idx]
        weight = parcel.weight_kg
        _length, _width, height = _footprint(parcel)

        column = _try_stack(parcel, weight, height, columns, vehicle)
        if column is None:
            column = _open_new_column(parcel, columns, row_state, vehicle)
            if column is None:
                return None
            z, layer = 0.0, 0
        else:
            z, layer = column.z_top, column.layers

        column.z_top = z + height
        column.layers = layer + 1
        # A fragile or non-stackable parcel must be the top of its column
        # from here on; everything else may still take more weight up to
        # its own limit.
        stackable = parcel.stackable if parcel.stackable is not None else True
        fragile = bool(parcel.fragile)
        max_stack_weight = parcel.max_stack_weight_kg if parcel.max_stack_weight_kg is not None else 0.0
        column.open_for_stacking = stackable and not fragile
        column.top_weight_limit = max_stack_weight

        placements[parcel.parcel_id] = Placement(
            parcel_id=parcel.parcel_id, x=column.x_start, y=column.y_start, z=z, layer=layer,
            load_sequence=load_sequence,
        )

    exceptions = []
    for i in range(n):
        for j in range(i + 1, n):
            a, b = parcels_in_delivery_order[i], parcels_in_delivery_order[j]
            if placements[a.parcel_id].x > placements[b.parcel_id].x:
                exceptions.append(
                    {
                        "parcel_a": a.parcel_id,
                        "parcel_b": b.parcel_id,
                        "reason": (
                            "Physical stacking/dimensional constraints forced a load "
                            "position that is not strictly LIFO relative to the delivery order."
                        ),
                    }
                )

    return PlacementResult(placements=placements, load_order_exceptions=exceptions)
