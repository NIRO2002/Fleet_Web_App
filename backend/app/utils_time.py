def minutes(value: str) -> int:
    h, m = map(int, value.split(":"))
    return h * 60 + m

def overlap_minutes(a_start, a_end, b_start, b_end):
    start = max(minutes(a_start), minutes(b_start))
    end = min(minutes(a_end), minutes(b_end))
    return max(0, end - start)

def time_window_compliance(parcels):
    """DEPRECATED (Phase 3, spec 3.2): measures whether parcels in the same
    vehicle *could* share a delivery window, not whether the vehicle can
    actually reach each one on time. Superseded by
    `app.optimization.assignment_problem.schedule_time_window_compliance`,
    which walks the vehicle's actual tour. Kept importable only so the
    dissertation can report the old pairwise metric alongside the new one
    for comparison, if useful — do not use it for constraint 5-style
    compliance in new code."""
    if len(parcels) <= 1:
        return 1.0

    pairs = 0
    compatible = 0
    for i in range(len(parcels)):
        for j in range(i + 1, len(parcels)):
            pairs += 1
            compatible += int(overlap_minutes(
                parcels[i].time_window_start, parcels[i].time_window_end,
                parcels[j].time_window_start, parcels[j].time_window_end
            ) > 0)
    return compatible / pairs if pairs else 1.0
