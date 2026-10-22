#!/usr/bin/env python3
"""Reproducible keyring tranche: isolated buses, HOME/XDG and private Sway only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sway', required=True, type=Path)
    args = parser.parse_args()
    if not args.sway.is_absolute() or not args.sway.is_file() or not os.access(args.sway, os.X_OK):
        parser.error('--sway must be an absolute executable (headless-capable)')
    root = Path(__file__).resolve().parents[2]
    output = Path(tempfile.mkdtemp(prefix='labfy-keyring-validation-'))
    # No SWAYSOCK, graphical bus, user configurations, secrets or session are
    # inherited. Every graphical test creates its own child headless compositor.
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1',
           'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software',
           'LABFY_TEST_SWAY': str(args.sway), 'LABFY_TEST_RENDERER': 'pixman',
           'LABFY_SESSION_V2_EVIDENCE': str(output / 'evidence')}
    for key in ('HOME', 'XDG_CONFIG_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME', 'XDG_RUNTIME_DIR'):
        target = output / key; target.mkdir(mode=0o700); env[key] = str(target)
    py = [sys.executable, '-B']
    checks = {
        'backend': [*py, '-m', 'unittest', 'discover', '-s', 'tests/session_v2', '-p', 'test_*.py'],
        'focus': [*py, 'quickshell/.config/quickshell/labfy-sway/tests/focus/test_focus.py'],
        'qml-unit': [*py, 'quickshell/.config/quickshell/labfy-sway/tests/focus/test_qml.py'],
        'qml-qt': ['/usr/lib/qt6/bin/qmltestrunner', '-input', 'tests/session_v2/qml', '-o', '-,txt'],
        **{name: [*py, 'tests/session_v2/' + filename + '.py'] for name, filename in (
            ('keyring-ui', 'keyring_ui'), ('keyring-runtime', 'keyring_runtime'),
            ('scratchpad-runtime', 'scratchpad_runtime'), ('phase3b-ui', 'phase3b_ui'),
            ('p0-runtime', 'p0_runtime'), ('path-runtime', 'path_stability_runtime'))},
        'diff-check': ['git', 'diff', '--check'],
    }
    results = {}
    print(output, flush=True)
    for name, argv in checks.items():
        with (output / (name + '.log')).open('w') as log:
            try: results[name] = subprocess.run(argv, cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=180).returncode
            except (OSError, subprocess.TimeoutExpired) as exc:
                log.write(str(exc) + '\n'); results[name] = 'UNAVAILABLE_OR_TIMEOUT'
        print(name, results[name], flush=True)
    (output / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
    return int(any(value != 0 for value in results.values()))


if __name__ == '__main__': sys.exit(main())
