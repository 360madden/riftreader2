"""Startup failures recover at most once; unavailable installations still fail."""
import tkinter as tk
import unittest
from unittest.mock import Mock, patch

from tests.tk_support import withdrawn_root


class TkStartupTests(unittest.TestCase):
    def test_transient_tcl_constructor_failure_also_gets_one_fresh_attempt(self):
        healthy = Mock()
        factory = Mock(side_effect=[tk.TclError("Can't find a usable init.tcl"), healthy])
        with patch('tests.tk_support._installed_libraries', return_value=True):
            self.assertIs(healthy, withdrawn_root(factory))
        self.assertEqual(2, factory.call_count)
        healthy.withdraw.assert_called_once()

    def test_transient_bootstrap_recreates_interpreter_then_withdraws(self):
        failed, healthy = Mock(), Mock()
        failed.loadtk.side_effect = tk.TclError('invalid command name "tcl_findLibrary"')
        factory = Mock(side_effect=[failed, healthy])
        with patch('tests.tk_support._installed_libraries', return_value=True):
            self.assertIs(healthy, withdrawn_root(factory))
        self.assertEqual(2, factory.call_count)
        failed.destroy.assert_called_once()
        healthy.withdraw.assert_called_once()

    def test_persistent_startup_failure_is_not_skipped_or_retried_forever(self):
        root = Mock()
        root.loadtk.side_effect = tk.TclError('invalid command name "tcl_findLibrary"')
        factory = Mock(return_value=root)
        with patch('tests.tk_support._installed_libraries', return_value=True):
            with self.assertRaisesRegex(tk.TclError, 'tcl_findLibrary'):
                withdrawn_root(factory)
        self.assertEqual(2, factory.call_count)

    def test_missing_installation_and_unrelated_errors_fail_immediately(self):
        for message, installed in (("Can't find a usable tk.tcl", False), ('version mismatch', True)):
            with self.subTest(message=message):
                root = Mock()
                root.loadtk.side_effect = tk.TclError(message)
                factory = Mock(return_value=root)
                with patch('tests.tk_support._installed_libraries', return_value=installed):
                    with self.assertRaises(tk.TclError):
                        withdrawn_root(factory)
                factory.assert_called_once()
