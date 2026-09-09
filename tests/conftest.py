"""
Put the repository root on sys.path so ``decklink.lib.*`` imports resolve.

``decklink`` has no ``__init__.py`` on purpose: OpenLP imports it as part of the
``contrib.plugins`` namespace package, and adding one would change how the
plugin is discovered.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
