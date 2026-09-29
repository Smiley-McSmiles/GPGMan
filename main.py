#!/usr/bin/env python3
"""
GPGMan - GTK4 and Libadwaita GPG / PGP Management Tool
"""

import os
import sys

# Ensure application directory is in Python module search path
APP_DIR = os.path.dirname(os.path.realpath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from gpgman.main import main

if __name__ == "__main__":
    sys.exit(main())
