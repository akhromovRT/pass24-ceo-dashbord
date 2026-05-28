"""Unit-тест на _forecast_mrr (P3.2 прогноз MRR)."""

from app.api.v1.dashboard import _forecast_mrr


def test_forecast_extrapolates_linear_growth():
    """История: 100, 110, 120, 130, 140, 150 — прогноз ~160, 170 на 2 месяца."""
    history = [
        {"year": 2026, "month": m, "sold_ap": None, "paid_ap": 90 + 10 * m} for m in range(1, 7)
    ]  # 100, 110, ..., 150
    out = _forecast_mrr(history, months=2)
    assert len(out) == 2
    assert out[0]["year"] == 2026 and out[0]["month"] == 7
    assert abs(out[0]["forecast_paid_ap"] - 160.0) < 0.01
    assert out[1]["year"] == 2026 and out[1]["month"] == 8
    assert abs(out[1]["forecast_paid_ap"] - 170.0) < 0.01
    # sold_ap/paid_ap для будущих месяцев = None
    assert out[0]["paid_ap"] is None


def test_forecast_handles_year_rollover():
    """Если последний месяц истории — декабрь, прогноз должен перейти на январь след. года."""
    history = [
        {"year": 2026, "month": 7, "sold_ap": None, "paid_ap": 100.0},
        {"year": 2026, "month": 8, "sold_ap": None, "paid_ap": 100.0},
        {"year": 2026, "month": 9, "sold_ap": None, "paid_ap": 100.0},
        {"year": 2026, "month": 10, "sold_ap": None, "paid_ap": 100.0},
        {"year": 2026, "month": 11, "sold_ap": None, "paid_ap": 100.0},
        {"year": 2026, "month": 12, "sold_ap": None, "paid_ap": 100.0},
    ]
    out = _forecast_mrr(history, months=3)
    assert [(r["year"], r["month"]) for r in out] == [
        (2027, 1),
        (2027, 2),
        (2027, 3),
    ]


def test_forecast_short_history_returns_empty():
    assert _forecast_mrr([{"year": 2026, "month": 1, "paid_ap": 100}], 5) == []


def test_forecast_clips_negative_to_zero():
    """Если регрессия даёт отрицательное значение — отдаём 0 (нельзя «минус факт»)."""
    history = [
        {"year": 2026, "month": m, "paid_ap": 100 - 20 * m} for m in range(1, 6)
    ]  # 80, 60, 40, 20, 0
    out = _forecast_mrr(history, months=3)
    # extrapolation даст отрицательные значения — клипнутся в 0
    assert all(r["forecast_paid_ap"] == 0.0 for r in out)
