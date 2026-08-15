def minutes(value: str) -> int:
    h, m = map(int, value.split(":"))
    return h * 60 + m

def overlap_minutes(a_start, a_end, b_start, b_end):
    start = max(minutes(a_start), minutes(b_start))
    end = min(minutes(a_end), minutes(b_end))
    return max(0, end - start)

def time_window_compliance(parcels):
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
