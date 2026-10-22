"""Campagne P0 privée : environnement positif, deux processus de test au plus.

CONTRACT : aucun socket réel hérité ; chaque scénario graphique crée son Lab.
Les preuves antérieures restent intactes dans un autre répertoire.
"""
import argparse
import concurrent.futures
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sway', default='/usr/bin/sway')
    parser.add_argument('--renderer', default='gles2')
    parser.add_argument('--evidence', default='build/p0-validation/campaign')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    base = (root / args.evidence).resolve()
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1',
           'QT_QPA_PLATFORM': 'offscreen', 'QT_QUICK_BACKEND': 'software',
           'LABFY_TEST_SWAY': str(Path(args.sway).resolve()), 'LABFY_TEST_RENDERER': args.renderer,
           'LABFY_SESSION_V2_EVIDENCE': str(base / 'evidence')}
    for key, folder in [('HOME', 'home'), ('XDG_CONFIG_HOME', 'config'), ('XDG_STATE_HOME', 'state'),
                        ('XDG_CACHE_HOME', 'cache'), ('XDG_RUNTIME_DIR', 'runtime')]:
        target = base / folder
        target.mkdir(exist_ok=True, mode=0o700)
        env[key] = str(target)
    tasks = {
        'unit': [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests/session_v2', '-p', 'test_*.py'],
        'focus': [sys.executable, '-B', 'quickshell/.config/quickshell/labfy-sway/tests/focus/test_focus.py'],
        'qml-python': [sys.executable, '-B', 'quickshell/.config/quickshell/labfy-sway/tests/focus/test_qml.py'],
        'qml-qt': ['/usr/lib/qt6/bin/qmltestrunner', '-input', 'tests/session_v2/qml', '-o', '-,txt'],
    }
    for name in ('runtime', 'failures', 'crashes', 'security', 'phase3b_runtime', 'phase3b_ui', 'p0_runtime', 'path_stability_runtime'):
        tasks[name] = [sys.executable, '-B', f'tests/session_v2/{name}.py']
    for case in ('natural', 'launch-failure-retry', 'preserve-empty-workspace', 'preserve-foreign',
                 'focus-third-party', 'focus-same-client', 'unowned-map', 'pinned-map',
                 'map-in-ipc-gap', 'provider-placement', 'crash-mid-ipc'):
        tasks['login-'+case] = [sys.executable, '-B', 'tests/session_v2/login_focus.py', '--case', case]
    def run(item):
        name, argv = item
        try:
            result = subprocess.run(argv, env=env, cwd=root, capture_output=True, text=True, timeout=600)
            code, output = result.returncode, result.stdout + result.stderr
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, output = 124, str(exc)
        (base / (name+'.log')).write_text(output)
        print(name, code, flush=True)
        return name, {'exit_code': code, 'command': argv}
    # Exécuter QtTest séparément pour conserver son diagnostic distinct des
    # scénarios Python/Wayland parallèles.
    qt_task = tasks.pop('qml-qt')
    name, result = run(('qml-qt', qt_task))
    results = {name: result}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results.update(pool.map(run, tasks.items()))
    (base / 'results.json').write_text(json.dumps({'sway': env['LABFY_TEST_SWAY'], 'renderer': args.renderer,
                                                 'results': results}, indent=2)+'\n')
    return int(any(row['exit_code'] for row in results.values()))


if __name__ == '__main__': raise SystemExit(main())
