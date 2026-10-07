#!/usr/bin/python3
"""Entrée native messaging ; jamais lancée via une commande fournie par message."""
import sys
sys.dont_write_bytecode = True
from session_v2.native_host import main
from session_v2.errors import Failure
try: main()
except (Failure, OSError): sys.exit(1)
