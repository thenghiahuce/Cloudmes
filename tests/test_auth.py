"""Unit tests for authentication without PostgreSQL or external API calls."""
import asyncio
import json
import time
import unittest
from unittest.mock import patch

from backend import auth


class PasswordAndTokenTests(unittest.TestCase):
    def test_password_roundtrip(self):
        stored = auth.hash_password('Long-Strong-Password-2026!')
        self.assertTrue(auth.verify_password('Long-Strong-Password-2026!', stored))
        self.assertFalse(auth.verify_password('wrong-password', stored))

    def test_password_unknown_scheme_fails(self):
        self.assertFalse(auth.verify_password('whatever', 'plain$password'))

    def test_valid_session_token(self):
        token = auth.make_token('staff-01', 'Nhan vien', 'technician')
        session = auth.read_token(token)
        self.assertEqual(session['username'], 'staff-01')
        self.assertEqual(session['role'], 'technician')

    def test_tampered_session_token_fails(self):
        token = auth.make_token('alice', 'Alice', 'admin')
        body, signature = token.split('.')
        mutated = ('X' if body[0] != 'X' else 'Y') + body[1:]
        self.assertIsNone(auth.read_token(mutated + '.' + signature))

    def test_expired_session_token_fails(self):
        with patch.object(auth.time, 'time', return_value=1000):
            token = auth.make_token('alice', 'Alice', 'admin')
        with patch.object(auth.time, 'time', return_value=1000 + auth.SESSION_SECONDS + 1):
            self.assertIsNone(auth.read_token(token))

    def test_invalid_role_fails(self):
        token = auth.make_token('alice', 'Alice', 'superadmin')
        self.assertIsNone(auth.read_token(token))

    def test_lock_after_five_failed_attempts(self):
        key = 'test-client|test-account'
        with patch.object(auth.time, 'time', return_value=1000):
            auth.clear_fails(key)
            for _ in range(5):
                auth.register_fail(key)
            self.assertTrue(auth.is_locked(key))
        with patch.object(auth.time, 'time', return_value=1301):
            self.assertFalse(auth.is_locked(key))
        auth.clear_fails(key)


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    async def call_app(self, path, role=None, type_='http'):
        messages = []
        visited = []
        async def downstream(scope, receive, send):
            visited.append(scope.get('state', {}).get('user'))
            await send({'type':'http.response.start','status':204,'headers':[]})
            await send({'type':'http.response.body','body':b''})
        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        async def send(message):
            messages.append(message)
        headers = []
        if role:
            token = auth.make_token('test-user', 'Test User', role)
            headers.append((b'cookie', ('session=' + token).encode()))
        scope = {'type':type_, 'path':path, 'method':'GET', 'headers':headers, 'state':{}}
        await auth.AuthMiddleware(downstream)(scope, receive, send)
        return messages, visited

    async def test_public_login_page(self):
        messages, visited = await self.call_app('/login')
        self.assertEqual(messages[0]['status'], 204)
        self.assertEqual(len(visited), 1)

    async def test_anonymous_ui_redirects(self):
        messages, visited = await self.call_app('/')
        self.assertEqual(messages[0]['status'], 302)
        self.assertIn((b'location', b'/login'), messages[0]['headers'])
        self.assertFalse(visited)

    async def test_anonymous_api_is_unauthorized(self):
        messages, visited = await self.call_app('/api/data')
        self.assertEqual(messages[0]['status'], 401)
        self.assertFalse(visited)

    async def test_technician_cannot_access_admin_routes(self):
        messages, visited = await self.call_app('/api/employees', 'technician')
        self.assertEqual(messages[0]['status'], 403)
        self.assertFalse(visited)

    async def test_admin_can_access_admin_routes(self):
        messages, visited = await self.call_app('/api/employees', 'admin')
        self.assertEqual(messages[0]['status'], 204)
        self.assertEqual(visited[0]['role'], 'admin')

    async def test_customer_cannot_access_ai_backend(self):
        messages, visited = await self.call_app('/api/vanna/chat', 'customer')
        self.assertEqual(messages[0]['status'], 403)
        self.assertFalse(visited)

    async def test_customer_can_access_own_order_endpoint(self):
        messages, visited = await self.call_app('/api/customer-orders', 'customer')
        self.assertEqual(messages[0]['status'], 204)
        self.assertEqual(len(visited), 1)


if __name__ == '__main__':
    unittest.main()
