from datetime import date

from app.parser.period_extraction import extract_periods


def test_explicit_slash_period():
    r = extract_periods("Оплата за 03/2026 за доступ к системе", date(2026, 3, 10))
    assert r.periods == [(2026, 3)]


def test_garbage_month_rejected():
    r = extract_periods("Договор № 10141-63/2020 оплата", date(2026, 3, 10))
    assert (2020, 63) not in r.periods
    assert all(1 <= m <= 12 for _, m in r.periods)


def test_contract_date_not_matched_as_period():
    r = extract_periods("Оплата по договору №233/1083-09/2020/П", date(2026, 3, 10))
    assert (2020, 9) not in r.periods


def test_month_name_with_year():
    r = extract_periods("Оплата за март 2026 за доступ", date(2026, 3, 10))
    assert (2026, 3) in r.periods


def test_month_name_without_year_infers_from_doc_date():
    r = extract_periods("за апрель доступ к системе", date(2026, 3, 28))
    assert r.periods == [(2026, 4)]


def test_month_range():
    r = extract_periods("оплата за период январь-июнь 2026", date(2026, 1, 15))
    assert r.periods == [(2026, m) for m in range(1, 7)]


def test_coverage_months_polgoda():
    r = extract_periods("Доступ к системе на полгода", date(2026, 3, 1))
    assert r.coverage_months == 6
    assert r.periods == []


def test_payment_kind_subscription():
    r = extract_periods("Доступ к системе PASS24.online", date(2026, 3, 1))
    assert r.payment_kind == "subscription"


def test_payment_kind_other():
    r = extract_periods("Оплата за оборудование и монтаж", date(2026, 3, 1))
    assert r.payment_kind == "other"
