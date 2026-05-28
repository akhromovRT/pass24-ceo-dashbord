from app.parser.classifier import ContractType, classify_contract


class TestClassifier:
    def test_subscription_by_p_suffix(self):
        result = classify_contract("Договор №123/П от 01.01.2025")
        assert result.type == ContractType.SUBSCRIPTION
        assert "/П" in result.rule or "/P" in result.rule

    def test_subscription_by_uslug_keyword(self):
        result = classify_contract("Договор на оказание услуг №45")
        assert result.type == ContractType.SUBSCRIPTION

    def test_subscription_by_abonent_keyword(self):
        result = classify_contract("Абонентский договор №12")
        assert result.type == ContractType.SUBSCRIPTION

    def test_equipment_by_montazh(self):
        result = classify_contract("Договор на монтаж СКУД №78")
        assert result.type == ContractType.EQUIPMENT

    def test_equipment_by_skud(self):
        result = classify_contract("Поставка СКУД оборудования")
        assert result.type == ContractType.EQUIPMENT

    def test_service_by_remont(self):
        result = classify_contract("Ремонт системы контроля доступа")
        assert result.type == ContractType.SERVICE

    def test_other_for_unknown(self):
        result = classify_contract("Прочий договор")
        assert result.type == ContractType.OTHER

    def test_equipment_by_large_amount(self):
        result = classify_contract("Договор №99", single_amount=150000)
        assert result.type == ContractType.EQUIPMENT
        assert "amount" in result.rule.lower() or "сумм" in result.rule.lower()

    def test_small_amount_not_equipment(self):
        result = classify_contract("Договор №99", single_amount=50000)
        assert result.type == ContractType.OTHER

    def test_source_is_auto(self):
        result = classify_contract("Абонентский договор")
        assert result.source == "auto"
