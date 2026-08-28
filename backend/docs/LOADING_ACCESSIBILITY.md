# Loading accessibility model

Loading accessibility is modeled as collision-free straight-line parcel
insertion from the cargo door at x=0 to the parcel's final axis-aligned
position. This is a parcel-accessibility approximation, not a full human
ergonomic or robotic motion-planning model.

Completed placements produce a hard precedence graph. A deeper parcel must
precede every nearer-door parcel whose y and z envelopes intersect its swept
insertion corridor. A stacked parcel must also follow its direct physical
support. A deterministic topological sort assigns `load_sequence=1..N`; when
several parcels are eligible, reverse delivery order is the tie-breaker so
LIFO behavior is retained wherever physical constraints allow it. Delivery
sequence remains unchanged.

The packed layout is then replayed from an empty vehicle. Every step verifies
bounds, non-overlap, existing stack support, and a clear door-to-target
corridor. A precedence cycle or failed replay rejects that packing. Placement
then retries once in deterministic pure reverse-delivery packing order; if the
retry also fails, `attempt_placement()` returns `None` and the optimizer treats
the assignment as infeasible. Accessibility failures are never downgraded to
`load_order_exceptions`, which remain reporting-only LIFO deviations.

This model assumes a parcel enters at its final y/z alignment and translates
only along +x. It does not model worker body clearance, lifting ergonomics,
door aperture transitions, intermediate rotation, articulated paths, or
robot-arm kinematics.
