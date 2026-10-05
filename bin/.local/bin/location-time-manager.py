#!/usr/bin/env python3
"""Gestion locale du fuseau système et de la position solaire Appearance."""
import argparse
import fcntl
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys

import importlib.util

BASE = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'labfy-appearance/preferences.json'
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'labfy-appearance/effective.json'
LOCK = STATE.parent / 'wallpaper.lock'
ZONE_TAB = Path('/usr/share/zoneinfo/zone1970.tab')
ZONE_ROOT = Path('/usr/share/zoneinfo')
TZ_PATTERN = re.compile(r'^[A-Za-z0-9_+][A-Za-z0-9_+.-]*(?:/[A-Za-z0-9_+][A-Za-z0-9_+.-]*)*$')


def timezone_valid(value):
    # INVARIANT: une identité IANA ne peut jamais être un chemin relatif ou absolu.
    if not isinstance(value, str) or len(value) > 128 or not TZ_PATTERN.fullmatch(value):
        return False
    if any(part in ('.', '..') for part in value.split('/')):
        return False
    path = ZONE_ROOT / value
    return path.is_file() and path.resolve().is_relative_to(ZONE_ROOT.resolve())


def coordinates(latitude, longitude):
    # CONTRACT: aucune conversion permissive de NaN, booléen ou texte vide.
    def parse(raw, bound):
        if isinstance(raw, bool) or raw is None or str(raw).strip() == '':
            raise ValueError('Coordonnées invalides')
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise ValueError('Coordonnées invalides') from None
        if not math.isfinite(value) or not -bound <= value <= bound:
            raise ValueError('Coordonnées invalides')
        return value
    return parse(latitude, 90), parse(longitude, 180)


def decimal_coordinate(part, degree_digits):
    sign = -1 if part[0] == '-' else 1
    digits = part[1:]
    degree = int(digits[:degree_digits])
    minute = int(digits[degree_digits:degree_digits + 2])
    second = int(digits[degree_digits + 2:]) if len(digits) > degree_digits + 2 else 0
    if minute >= 60 or second >= 60:
        raise ValueError('Coordonnées zone1970.tab invalides')
    return sign * (degree + minute / 60 + second / 3600)


def presets(path=ZONE_TAB):
    # CONTRACT: zone1970.tab est une base locale représentative ; ses points
    # ne prétendent jamais être la position exacte de l'utilisateur.
    result = []
    for line in path.read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        fields = line.split('\t')
        if len(fields) < 3:
            continue
        countries, compact, timezone = fields[:3]
        match = re.fullmatch(r'([+-]\d{4}(?:\d{2})?)([+-]\d{5}(?:\d{2})?)', compact)
        if not match or not timezone_valid(timezone):
            continue
        latitude = decimal_coordinate(match.group(1), 2)
        longitude = decimal_coordinate(match.group(2), 3)
        coordinates(latitude, longitude)
        result.append({'timezone': timezone, 'latitude': latitude, 'longitude': longitude,
                       'countries': countries.split(','), 'comment': fields[3] if len(fields) > 3 else '',
                       'city': timezone.split('/')[-1].replace('_', ' ')})
    return sorted(result, key=lambda item: item['timezone'])


def search(entries, query):
    query = query.strip().casefold()
    return [entry for entry in entries if query in ' '.join((entry['timezone'], entry['city'], entry['comment'],
             ' '.join(entry['countries']))).casefold()]


def current_timezone():
    result = subprocess.run(['timedatectl', 'show', '-p', 'Timezone', '--value'],
                            capture_output=True, text=True, check=True, timeout=10)
    return result.stdout.strip()


def set_timezone(timezone):
    if not timezone_valid(timezone):
        raise ValueError('Fuseau horaire invalide')
    # WHY: timedated demande l'authentification Polkit de la session. Le mot
    # de passe ne traverse jamais QuickShell ni ce processus Python.
    subprocess.run(['timedatectl', 'set-timezone', timezone], check=True,
                   capture_output=True, text=True, timeout=120)
    if current_timezone() != timezone:
        raise RuntimeError('Le fuseau système ne correspond pas à la demande')


def night_module():
    spec = importlib.util.spec_from_file_location('night_light_manager', BASE / 'night-light-manager.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.CONFIG, module.STATE, module.LOCK = CONFIG, STATE, LOCK
    return module


def read_preferences(night):
    return night.normalized(night.read_json(CONFIG))


def saved_locations(pref):
    locations = pref.get('savedLocations', [])
    if not isinstance(locations, list) or len(locations) > 100:
        raise ValueError('Liste de lieux invalide')
    for entry in locations:
        if not isinstance(entry, dict) or not isinstance(entry.get('name'), str) \
                or not entry['name'].strip() or len(entry['name']) > 80 \
                or not timezone_valid(entry.get('timezone')):
            raise ValueError('Lieu enregistré invalide')
        coordinates(entry.get('latitude'), entry.get('longitude'))
    return locations


def location_name(value, required=False):
    if not isinstance(value, str) or len(value.strip()) > 80 or '\n' in value or '\r' in value \
            or (required and not value.strip()):
        raise ValueError('Nom de lieu invalide')
    return value.strip()


def public_state():
    night = night_module()
    pref = read_preferences(night)
    locations = saved_locations(pref)
    # WHY: la position solaire courante n'est jamais renvoyée à la page ; seuls
    # les lieux enregistrés portent leurs coordonnées pour pouvoir être rejoués.
    return {'effectiveTimezone': current_timezone(), 'solarScheduleConfigured':
            'latitude' in pref and 'longitude' in pref,
            'activeLocationName': pref.get('activeLocationName', ''),
            'savedLocations': locations}


def apply(kind, timezone=None, latitude=None, longitude=None, name=None):
    if kind in ('timezone', 'both') and not timezone_valid(timezone):
        raise ValueError('Fuseau horaire invalide')
    if kind in ('solar', 'both'):
        lat, lon = coordinates(latitude, longitude)
        if name is not None:
            name = location_name(name)
    night = night_module()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before_tz = current_timezone()
        before_bytes = CONFIG.read_bytes() if CONFIG.exists() else None
        before_pref = read_preferences(night)
        suspended = night.suspended_state()
        changed_tz = False
        changed_solar = False
        try:
            if kind in ('timezone', 'both') and timezone != before_tz:
                set_timezone(timezone)
                changed_tz = True
            if kind in ('solar', 'both'):
                pref = dict(before_pref)
                pref.update(latitude=lat, longitude=lon)
                if name is not None:
                    pref['activeLocationName'] = name
                else:
                    pref.pop('activeLocationName', None)
                night.atomic_json(CONFIG, pref)
                changed_solar = True
                # CONTRACT: Auto seul redémarre avec les nouvelles coordonnées.
                # ON conserve sa température forcée ; OFF et Sun restent éteints.
                if pref['nightLightMode'] == 'auto' and not suspended:
                    night.apply_service(pref, False)
                else:
                    night.verify(pref, suspended)
            if kind in ('timezone', 'both') and current_timezone() != timezone:
                raise RuntimeError('Vérification du fuseau système échouée')
            return public_state()
        except Exception as original_error:
            rollback_errors = []
            if changed_solar:
                try:
                    night.restore(CONFIG, before_bytes)
                    if before_pref['nightLightMode'] == 'auto' and not suspended:
                        night.apply_service(before_pref, False)
                except Exception:
                    rollback_errors.append('position solaire ou Night Light')
            if changed_tz:
                try:
                    set_timezone(before_tz)
                except Exception:
                    rollback_errors.append('fuseau système')
            if rollback_errors:
                raise RuntimeError('Échec de transaction ; rollback incomplet : '
                                   + ', '.join(rollback_errors)) from original_error
            raise


def save_location(name, timezone, latitude, longitude):
    name = location_name(name, required=True)
    if not timezone_valid(timezone):
        raise ValueError('Fuseau horaire invalide')
    lat, lon = coordinates(latitude, longitude)
    night = night_module()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, 'a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        pref = read_preferences(night)
        locations = saved_locations(pref)
        item = {'name': name.strip(), 'timezone': timezone, 'latitude': lat, 'longitude': lon}
        pref['savedLocations'] = [entry for entry in locations if entry.get('name') != item['name']] + [item]
        night.atomic_json(CONFIG, pref)
    return public_state()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('status')
    listing = sub.add_parser('list')
    listing.add_argument('query', nargs='?', default='')
    for kind in ('timezone', 'solar', 'both'):
        command = sub.add_parser('apply-' + kind)
        if kind in ('timezone', 'both'):
            command.add_argument('timezone')
        if kind in ('solar', 'both'):
            command.add_argument('latitude')
            command.add_argument('longitude')
            command.add_argument('--name')
    save = sub.add_parser('save')
    for field in ('name', 'timezone', 'latitude', 'longitude'):
        save.add_argument(field)
    args = parser.parse_args()
    try:
        if args.action == 'status': result = public_state()
        elif args.action == 'list': result = search(presets(), args.query)
        elif args.action == 'save': result = save_location(args.name, args.timezone, args.latitude, args.longitude)
        else: result = apply(args.action.removeprefix('apply-'),
                             getattr(args, 'timezone', None), getattr(args, 'latitude', None),
                             getattr(args, 'longitude', None), getattr(args, 'name', None))
        print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, BlockingIOError) as exc:
        # CONTRACT: aucune coordonnée privée dans les messages d'erreur.
        print('Erreur : ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
