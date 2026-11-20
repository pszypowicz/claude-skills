"""Shared helpers for the unifi plugin tests."""

import importlib.machinery
import importlib.util
import os

TESTS = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(TESTS)
BIN = os.path.join(PLUGIN, "bin")
LIBEXEC = os.path.join(PLUGIN, "libexec")


def load_script(name):
    """Import an extensionless script from bin/ as a module."""
    path = os.path.join(BIN, name)
    module_name = name.replace("-", "_")
    loader = importlib.machinery.SourceFileLoader(module_name, path)
    spec = importlib.util.spec_from_loader(module_name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module
