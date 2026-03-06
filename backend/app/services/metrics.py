def calculate_payment_score(
    on_time_pct: float,
    collectability: float,
    tenure_months: int,
    debt_ratio: float,
) -> int:
    tenure_score = min(tenure_months / 48, 1.0) * 100
    debt_score = max(0, 100 - debt_ratio)

    raw = (
        on_time_pct * 0.4
        + collectability * 0.3
        + tenure_score * 0.2
        + debt_score * 0.1
    )
    return int(max(0, min(100, raw)))
