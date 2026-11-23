"""Unit tests for scope selection; no live database required."""
import unittest
from unittest.mock import patch

from backend import scope


class ScopeTests(unittest.TestCase):
    def test_no_access_by_default(self):
        self.assertTrue(scope.NO_ACCESS.is_empty)
        self.assertEqual(scope.NO_ACCESS.db_role, 'ai_scoped')

    def test_admin_role_uses_read_only_admin_role(self):
        s = scope.Scope(username='admin', role='admin', all_machines=True)
        self.assertFalse(s.is_empty)
        self.assertEqual(s.db_role, 'ai_admin')

    def test_technician_with_machines(self):
        s = scope.Scope(username='tech', role='technician', machine_ids=(3, 8))
        self.assertFalse(s.is_empty)
        self.assertEqual(s.db_role, 'ai_scoped')

    def test_missing_user_returns_no_access(self):
        with patch.object(scope, 'fetch_all', return_value=[]):
            self.assertEqual(scope.load_scope('absent'), scope.NO_ACCESS)

    def test_admin_loaded_from_db(self):
        with patch.object(scope, 'fetch_all', return_value=[{'role':'admin', 'machine_ids':None}]):
            s = scope.load_scope('admin')
        self.assertTrue(s.all_machines)
        self.assertEqual(s.db_role, 'ai_admin')

    def test_assigned_machines_are_sorted(self):
        with patch.object(scope, 'fetch_all', return_value=[{'role':'technician','machine_ids':[8,3,8]}]):
            s = scope.load_scope('tech')
        self.assertEqual(s.machine_ids, (3,8,8))

    def test_no_username_fails_closed(self):
        with patch.object(scope,'fetch_all') as fetch:
            self.assertEqual(scope.load_scope(None), scope.NO_ACCESS)
            fetch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
