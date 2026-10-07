#!/usr/bin/python3
"""Entrée V2 indépendante ; aucun import QuickShell/V1."""
import sys
sys.dont_write_bytecode = True
from session_v2.cli import main
sys.exit(main())
