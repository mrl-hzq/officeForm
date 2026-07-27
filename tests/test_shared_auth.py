from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from app import create_app


class SharedPasswordAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            AUTH_SHARED_PASSWORD="test-shared-password",
            JWT_SECRET_KEY="test-jwt-secret",
        )
        self.client = self.app.test_client()

    @patch("app.auth._get_auth_worker", return_value={"workerId": "C0036", "role": "worker"})
    @patch("app.auth.query_one", return_value={"id": 1, "password_hash": None})
    def test_login_rejects_wrong_password(
        self,
        _query_one: Mock,
        _get_auth_worker: Mock,
    ) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={"workerId": "C0036", "password": "wrong"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json(), {"error": "Invalid password."})

    @patch("app.auth._get_auth_worker", return_value={"workerId": "C0036", "role": "worker"})
    @patch("app.auth.query_one", return_value={"id": 1, "password_hash": None})
    def test_login_accepts_shared_password(
        self,
        _query_one: Mock,
        _get_auth_worker: Mock,
    ) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={"workerId": "C0036", "password": "test-shared-password"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.get_json())

    @patch("app.auth._get_auth_worker", return_value={"workerId": "C0036", "role": "worker"})
    @patch("app.auth.query_one", return_value={"id": 1, "password_hash": None})
    def test_login_accepts_personal_password(
        self,
        _query_one: Mock,
        _get_auth_worker: Mock,
    ) -> None:
        from werkzeug.security import generate_password_hash
        _query_one.return_value = {"id": 1, "password_hash": generate_password_hash("mypersonal")}

        response = self.client.post(
            "/api/auth/login",
            json={"workerId": "C0036", "password": "mypersonal"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("token", response.get_json())

    @patch("app.auth.query_one")
    def test_registration_rejects_short_password(self, query_one: Mock) -> None:
        response = self.client.post(
            "/api/auth/register",
            json={"workerId": "NEW001", "password": "ab"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {"error": "Password must be at least 4 characters."})
        query_one.assert_not_called()

    @patch("app.auth._get_auth_worker", return_value={"workerId": "NEW001", "role": "worker"})
    @patch("app.auth.get_db")
    @patch("app.auth.query_one", return_value=None)
    def test_registration_stores_hashed_password(
        self,
        _query_one: Mock,
        get_db: Mock,
        _get_auth_worker: Mock,
    ) -> None:
        database = Mock()
        cursor = Mock()
        database.cursor.return_value = cursor
        get_db.return_value = database

        response = self.client.post(
            "/api/auth/register",
            json={"workerId": "NEW001", "password": "mypassword"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("token", response.get_json())
        database.begin.assert_called_once_with()
        # Verify password_hash was stored (second argument to execute)
        insert_call = cursor.execute.call_args_list[0]
        self.assertEqual(insert_call[0][0], "INSERT INTO users (worker_id, password_hash) VALUES (%s, %s)")
        self.assertEqual(insert_call[0][1][0], "NEW001")
        stored_hash = insert_call[0][1][1]
        self.assertIsNotNone(stored_hash)
        self.assertNotEqual(stored_hash, "mypassword")
        database.commit.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
