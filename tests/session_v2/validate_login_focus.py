"""Validation bornée dans une copie privée, sans environnement de session réel."""
from pathlib import Path
import concurrent.futures
import json
import os
import subprocess
import sys
root = Path(__file__).resolve().parents[2]
base = root / 'build/real-focus-env'
base.mkdir(parents=True, exist_ok=True, mode=0o700)
for folder in ('home', 'config', 'state', 'cache', 'runtime'):
    (base / folder).mkdir(exist_ok=True, mode=0o700)
env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'}
# Sélections de test explicites seulement ; aucun environnement graphique/bus
# ou fichier de configuration hérité du bureau n'entre dans les enfants.
for key in ('LABFY_TEST_SWAY', 'LABFY_TEST_RENDERER'):
    if key in os.environ: env[key] = os.environ[key]
fallback = Path('/tmp/limusic-test-sway-1.12/usr/bin/sway')
if 'LABFY_TEST_SWAY' not in env and fallback.is_file() and os.access(fallback, os.X_OK):
    env.update(LABFY_TEST_SWAY=str(fallback), LABFY_TEST_RENDERER='pixman')
for key, folder in (('HOME','home'),('XDG_CONFIG_HOME','config'),('XDG_STATE_HOME','state'),('XDG_CACHE_HOME','cache'),('XDG_RUNTIME_DIR','runtime')):
    env[key] = str(base / folder)
env.update(PYTHONDONTWRITEBYTECODE='1', QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software')
tasks = {
 'focus': [sys.executable,'-B','quickshell/.config/quickshell/labfy-sway/tests/focus/test_focus.py'],
 'backend': [sys.executable,'-B','-m','unittest','discover','-s','tests/session_v2','-p','test_*.py'],
 'qml-python': [sys.executable,'-B','quickshell/.config/quickshell/labfy-sway/tests/focus/test_qml.py'],
 'qml-qt': ['/usr/lib/qt6/bin/qmltestrunner','-input','tests/session_v2/qml','-o','-,txt'],
 'checkpoint-fixture': [sys.executable,'-B','-c',"import sys; sys.path.insert(0, 'tests/session_v2'); from login_focus import checkpoint; print(checkpoint()['focus'])"],
 'diff-check': ['git','diff','--check'],
}
for case in ('natural', 'launch-failure-retry', 'preserve-empty-workspace', 'preserve-foreign', 'focus-third-party', 'focus-same-client', 'unowned-map', 'pinned-map', 'map-in-ipc-gap', 'provider-placement', 'crash-mid-ipc', 'autotiling', 'focus-helper-late', 'focus-external-late', 'focus-finish-late'):
    tasks['login-'+case] = [sys.executable,'-B','tests/session_v2/login_focus.py','--case',case]
def run(item):
    name, argv = item
    try:
        result = subprocess.run(argv, env=env, cwd=root, capture_output=True, text=True, timeout=90)
        code, output = result.returncode, result.stdout + result.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        code, output = 124, str(exc)
    (base / (name+'.log')).write_text(output)
    return name, {'exit_code': code, 'output': output}
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    results = dict(pool.map(run, tasks.items()))
(base / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2)+'\n')
for name, result in results.items(): print(name, result['exit_code'], result['output'][-1800:])
raise SystemExit(1 if any(result['exit_code'] for result in results.values()) else 0)
