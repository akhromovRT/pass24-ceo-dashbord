from app.services.metrics import calculate_payment_score


class TestPaymentScore:
    def test_perfect_payer(self):
        score = calculate_payment_score(
            on_time_pct=100, collectability=100, tenure_months=48, debt_ratio=0
        )
        assert score >= 90

    def test_bad_payer(self):
        score = calculate_payment_score(
            on_time_pct=20, collectability=40, tenure_months=3, debt_ratio=80
        )
        assert score <= 30

    def test_range_always_0_100(self):
        for on_time in [0, 50, 100]:
            for collect in [0, 50, 100]:
                for tenure in [0, 12, 60]:
                    for debt in [0, 50, 100]:
                        score = calculate_payment_score(on_time, collect, tenure, debt)
                        assert 0 <= score <= 100, f"Out of range: {score}"

    def test_medium_payer(self):
        score = calculate_payment_score(
            on_time_pct=70, collectability=60, tenure_months=24, debt_ratio=30
        )
        assert 40 <= score <= 70

    def test_zero_tenure(self):
        score = calculate_payment_score(
            on_time_pct=100, collectability=100, tenure_months=0, debt_ratio=0
        )
        assert score >= 70  # Still good but lower due to no tenure
