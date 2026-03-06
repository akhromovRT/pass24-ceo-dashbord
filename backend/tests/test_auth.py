from app.core.security import get_password_hash, verify_password, create_access_token


class TestSecurity:
    def test_password_hash_and_verify(self):
        password = "testpassword123"
        hashed = get_password_hash(password)
        assert hashed != password
        assert verify_password(password, hashed)
        assert not verify_password("wrong", hashed)

    def test_create_access_token(self):
        token = create_access_token(data={"sub": "test@test.ru"})
        assert isinstance(token, str)
        assert len(token) > 50

    def test_different_data_different_tokens(self):
        t1 = create_access_token(data={"sub": "a@a.ru"})
        t2 = create_access_token(data={"sub": "b@b.ru"})
        assert t1 != t2
