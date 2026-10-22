#!/usr/bin/env python3
"""Reproducible isolated scratchpad validation; never uses the desktop socket."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sway', required=True, type=Path, help='absolute headless-capable Sway executable')
    parser.add_argument('--renderer', default='pixman', choices=('pixman', 'gles2'))
    args = parser.parse_args()
    if not args.sway.is_absolute() or not args.sway.is_file() or not os.access(args.sway, os.X_OK):
        parser.error('--sway must be an existing absolute executable')
    root = Path(__file__).resolve().parents[2]
    output = Path(tempfile.mkdtemp(prefix='labfy-scratchpad-validation-', dir='/tmp'))
    # CONTRACT : positive environment list; no graphical bus/socket, user state,
    # test override for backend imports or configuration reaches subprocesses.
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1',
           'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software',
           'LABFY_TEST_SWAY': str(args.sway), 'LABFY_TEST_RENDERER': args.renderer,
           'LABFY_SESSION_V2_EVIDENCE': str(output / 'evidence')}
    for key in ('HOME', 'XDG_CONFIG_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME', 'XDG_RUNTIME_DIR'):
        path = output / key
        path.mkdir(mode=0o700)
        env[key] = str(path)
    checks = {
        'backend': [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests/session_v2', '-p', 'test_*.py'],
        'focus': [sys.executable, '-B', 'quickshell/.config/quickshell/labfy-sway/tests/focus/test_focus.py'],
        'qml-python': [sys.executable, '-B', 'quickshell/.config/quickshell/labfy-sway/tests/focus/test_qml.py'],
        'qml-qt': ['/usr/lib/qt6/bin/qmltestrunner', '-input', 'tests/session_v2/qml', '-o', '-,txt'],
        'scratchpad-runtime': [sys.executable, '-B', 'tests/session_v2/scratchpad_runtime.py'],
        'diff-check': ['git', 'diff', '--check'],
    }
    results = {}
    print(output, flush=True)
    for name, argv in checks.items():
        with (output / (name + '.log')).open('w') as log:
            try:
                result = subprocess.run(argv, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
                results[name] = result.returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                log.write(str(exc) + '\n')
                results[name] = 'UNAVAILABLE_OR_TIMEOUT'
        print(name, results[name], flush=True)
    (output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    return int(any(value != 0 for value in results.values()))


if __name__ == '__main__':
    sys.exit(main())
