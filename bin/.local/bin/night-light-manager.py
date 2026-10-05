#!/usr/bin/env python3
"""Préférences Night Light locales et cycle de vie de l'unique wlsunset.service."""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'labfy-appearance/preferences.json'
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'labfy-appearance/effective.json'
LOCK = STATE.parent / 'wallpaper.lock'
UNIT = 'wlsunset.service'
WLSUNSET = '/usr/bin/wlsunset'
MODES = ('off', 'auto', 'on')
MIN_NIGHT, MAX_NIGHT, STEP = 2500, 5000, 100
DAY_TEMPERATURE = 6500


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return {}


def atomic_json(path, value):
    # CONTRACT: préférences et état sont chacun publiés par replace durable ;
    # les permissions 0600 protègent les coordonnées locales hors Git.
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.night-light-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def restore(path, old):
    if old is None:
        path.unlink(missing_ok=True)
    else:
        fd, temporary = tempfile.mkstemp(prefix='.night-light-rollback-', dir=path.parent)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(old)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)


def temperature(value):
    # INVARIANT: aucun arrondi implicite ni NaN ne peut devenir un argument CLI.
    if isinstance(value, bool) or not isinstance(value, int) or not MIN_NIGHT <= value <= MAX_NIGHT or value % STEP:
        raise ValueError('Température de nuit invalide (2500–5000 K, pas de 100 K)')
    return value


def coordinates(pref):
    try:
        lat, lon = float(pref['latitude']), float(pref['longitude'])
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
            raise ValueError()
        return str(pref['latitude']), str(pref['longitude'])
    except (KeyError, TypeError, ValueError):
        raise ValueError('Planification à configurer') from None


def normalized(pref):
    result = dict(pref)
    mode = result.get('nightLightMode', 'auto' if 'latitude' in result and 'longitude' in result else 'off')
    if mode not in MODES:
        raise ValueError('Mode Night Light invalide')
    result.update(version=max(3, int(result.get('version', 2))),
                  nightLightMode=mode,
                  nightTemperature=temperature(result.get('nightTemperature', 3000)),
                  dayTemperature=result.get('dayTemperature', DAY_TEMPERATURE),
                  scheduleType=result.get('scheduleType', 'solar'))
    if result['dayTemperature'] != DAY_TEMPERATURE or result['scheduleType'] != 'solar':
        raise ValueError('Configuration Night Light non prise en charge')
    if mode == 'auto':
        coordinates(result)
    return result


def effective(mode, suspended=False):
    # CONTRACT 17F: une suspension Soleil n'écrase jamais le choix utilisateur.
    return 'off' if suspended else mode


def argv(pref):
    pref = normalized(pref)
    mode = effective(pref['nightLightMode'])
    if mode == 'off':
        return None
    temperatures = ['-t', str(pref['nightTemperature']), '-T', str(pref['dayTemperature'])]
    if mode == 'auto':
        lat, lon = coordinates(pref)
        return [WLSUNSET, '-l', lat, '-L', lon, *temperatures]
    # WHY: wlsunset 0.4.0 refuse -T == -t. Un horaire manuel valide démarre
    # le processus ; ExecStartPost sélectionne ensuite FORCE_LOW via SIGUSR1.
    return [WLSUNSET, '-S', '06:00', '-s', '18:00', *temperatures]


def systemctl(*args):
    result = subprocess.run(['systemctl', '--user', *args], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError('Échec de gestion de wlsunset.service')
    return result.stdout.strip()


def unit_state():
    lines = systemctl('show', UNIT, '-p', 'ActiveState', '-p', 'MainPID').splitlines()
    fields = dict(line.split('=', 1) for line in lines if '=' in line)
    return fields.get('ActiveState') == 'active', int(fields.get('MainPID', '0'))


def wlsunset_pids():
    # INVARIANT: inspection seule ; aucun pkill/killall global n'est permis.
    found = []
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            # Le nom du processus couvre aussi un lancement externe par PATH.
            if (entry / 'comm').read_text(encoding='ascii').strip() == 'wlsunset':
                found.append(int(entry.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    return found


def verify(pref):
    active, main_pid = unit_state()
    pids = wlsunset_pids()
    mode = effective(pref['nightLightMode'])
    if mode == 'off':
        if active or pids:
            raise RuntimeError('Night Light Off : wlsunset encore actif')
    elif not active or pids != [main_pid]:
        raise RuntimeError('wlsunset absent, dupliqué ou hors unité systemd')
    else:
        actual = (Path('/proc') / str(main_pid) / 'cmdline').read_bytes().split(b'\0')[:-1]
        if actual != [part.encode() for part in argv(pref)]:
            raise RuntimeError('Arguments wlsunset incohérents')


def apply_service(pref):
    mode = effective(pref['nightLightMode'])
    systemctl('stop' if mode == 'off' else 'restart', UNIT)
    verify(pref)


def snapshot(pref, state):
    return {'nightLightMode': pref['nightLightMode'],
            'effectiveNightLightMode': effective(pref['nightLightMode'], state.get('nightLightSuspended', False)),
            'nightLightSuspended': bool(state.get('nightLightSuspended', False)),
            'nightTemperature': pref['nightTemperature'], 'dayTemperature': pref['dayTemperature'],
            'scheduleType': pref['scheduleType'], 'scheduleConfigured': 'latitude' in pref and 'longitude' in pref}


def publish(value):
    payload = json.dumps(value, separators=(',', ':'))
    try:
        result = subprocess.run(['qs', '-c', 'labfy-sway', 'ipc', 'call', 'appearance', 'publishNightLight', payload],
                                text=True, capture_output=True)
    except FileNotFoundError:
        return
    # QuickShell peut être absent ; systemd et les préférences restent autonomes.
    if result.returncode == 0 and result.stdout.strip() != 'true':
        raise RuntimeError('QuickShell a refusé l’état Night Light')


def change(mode=None, night=None):
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        old_pref_bytes = CONFIG.read_bytes() if CONFIG.exists() else None
        old_state_bytes = STATE.read_bytes() if STATE.exists() else None
        old_pref = normalized(read_json(CONFIG))
        pref = dict(old_pref)
        if mode is not None:
            if mode not in MODES:
                raise ValueError('Mode Night Light invalide')
            pref['nightLightMode'] = mode
        if night is not None:
            pref['nightTemperature'] = temperature(night)
        pref = normalized(pref)
        state = read_json(STATE)
        previous_mode = old_pref['nightLightMode']
        if pref == old_pref:
            verify(pref)
            return snapshot(pref, state)
        new_state = dict(state)
        new_state.update(effectiveNightLightMode=effective(pref['nightLightMode']),
                         nightLightSuspended=False)
        try:
            atomic_json(CONFIG, pref)
            apply_service(pref)
            atomic_json(STATE, new_state)
            result = snapshot(pref, new_state)
            publish(result)
            return result
        except Exception:
            restore(CONFIG, old_pref_bytes)
            restore(STATE, old_state_bytes)
            try:
                apply_service(old_pref)
            except Exception as rollback_error:
                raise RuntimeError('Échec Night Light et rollback du service') from rollback_error
            raise


def reconcile():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pref = normalized(read_json(CONFIG))
        state = read_json(STATE)
        try:
            verify(pref)
        except RuntimeError:
            # Une instance étrangère ne peut être supprimée par cette unité.
            active, main_pid = unit_state()
            if any(pid != main_pid for pid in wlsunset_pids()):
                raise RuntimeError('wlsunset externe détecté ; réconciliation refusée')
            apply_service(pref)
        state.update(effectiveNightLightMode=effective(pref['nightLightMode']),
                     nightLightSuspended=False)
        if read_json(CONFIG) != pref:
            atomic_json(CONFIG, pref)
        if read_json(STATE) != state:
            atomic_json(STATE, state)
        return snapshot(pref, state)


def launch():
    pref = normalized(read_json(CONFIG))
    command = argv(pref)
    if command is None:
        return 0
    os.execv(command[0], command)


def post_start():
    pref = normalized(read_json(CONFIG))
    if pref['nightLightMode'] != 'on':
        return 0
    # systemd ne fournit pas MAINPID dans cet ExecStartPost sur cette version.
    # Interroger le PID de l'unité et attendre la fin de l'exec Python -> wlsunset.
    deadline = time.monotonic() + 3
    pid = 0
    while time.monotonic() < deadline:
        pid = int(systemctl('show', '-P', 'MainPID', UNIT) or '0')
        try:
            if pid > 0 and (Path('/proc') / str(pid) / 'cmdline').read_bytes().startswith(WLSUNSET.encode() + b'\0'):
                break
        except FileNotFoundError:
            pass
        time.sleep(0.1)
    else:
        raise RuntimeError('PID wlsunset principal invalide')
    # CONTRACT: SIGUSR1 parcourt AUTO -> FORCE_HIGH -> FORCE_LOW en 0.4.0.
    # Laisser l'event loop traiter chaque signal pour ne jamais perdre un cran.
    time.sleep(0.3)
    os.kill(pid, signal.SIGUSR1)
    time.sleep(0.3)
    os.kill(pid, signal.SIGUSR1)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('current', 'reconcile', 'validate', 'launch', 'post-start'):
        sub.add_parser(action)
    sub.add_parser('set-mode').add_argument('mode')
    sub.add_parser('set-night-temperature').add_argument('value')
    args = parser.parse_args()
    try:
        if args.action == 'launch':
            return launch()
        if args.action == 'post-start':
            return post_start()
        if args.action == 'reconcile':
            result = reconcile()
        elif args.action == 'set-mode':
            result = change(mode=args.mode)
        elif args.action == 'set-night-temperature':
            if not args.value.isdecimal():
                raise ValueError('Température de nuit invalide')
            result = change(night=int(args.value))
        else:
            pref = normalized(read_json(CONFIG))
            result = snapshot(pref, read_json(STATE))
            if args.action == 'current':
                verify(pref)
        print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
        return 0
    except (OSError, ValueError, RuntimeError, BlockingIOError) as exc:
        print('Erreur : ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
