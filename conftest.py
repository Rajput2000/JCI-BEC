"""Ensures the project root is importable from tests/ (which has no
__init__.py), regardless of the directory pytest is invoked from."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
