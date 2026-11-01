#!/usr/bin/env python3
"""Lectures matérielles bornées, en lecture seule ; un appel produit un instantané JSON."""
import json
import os
from pathlib import Path
import re
import sys
import time

PROC = Path('/proc')
SYS = Path('/sys')


def read(path):
    try:
        return path.read_text(encoding='ascii').strip()
    except (OSError, UnicodeError):
        return None


def number(path, scale=1):
    value = read(path)
    try:
        return int(value) / scale if value is not None else None
    except ValueError:
        return None


def cpu_ticks(text):
    """CONTRACT: guest et guest_nice sont déjà inclus dans user et nice."""
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if not fields or not re.fullmatch(r'cpu\d*', fields[0]):
            continue
        try:
            values = [int(x) for x in fields[1:9]]
        except ValueError:
            continue
        if len(values) < 8:
            continue
        result[fields[0]] = [sum(values), values[3] + values[4]]
    return result


def meminfo(text):
    values = {m.group(1): int(m.group(2)) * 1024 for m in
              re.finditer(r'^(\w+):\s+(\d+) kB$', text, re.M)}
    total = values.get('MemTotal')
    available = values.get('MemAvailable')
    return {'total': total, 'available': available,
            'used': max(0, total - available) if total is not None and available is not None else None,
            'cache': values.get('Cached'), 'buffers': values.get('Buffers'),
            'swapTotal': values.get('SwapTotal'), 'swapUsed':
                max(0, values['SwapTotal'] - values['SwapFree'])
                if 'SwapTotal' in values and 'SwapFree' in values else None}


def psi(text):
    result = {}
    for kind in ('some', 'full'):
        match = re.search(r'^' + kind + r'\s+avg10=([\d.]+)\s+avg60=([\d.]+)\s+avg300=([\d.]+)', text, re.M)
        result[kind] = [float(x) for x in match.groups()] if match else None
    return result


def zram(text):
    try:
        values = [int(x) for x in text.split()]
        if len(values) < 3:
            return None
        logical, compressed, consumed = values[:3]
        return {'logical': logical, 'compressed': compressed, 'consumed': consumed,
                'ratio': logical / compressed if compressed else None}
    except ValueError:
        return None


def gpu_frequency(text):
    # amdgpu exposes the selected DPM level with '*'; absent data stays absent.
    for line in text.splitlines():
        if '*' in line:
            match = re.search(r'(\d+)Mhz', line, re.I)
            if match:
                return int(match.group(1))
    return None


def gpu():
    # INVARIANT: cardN et hwmonN sont découverts par identité, jamais par indice fixe.
    for card in sorted((SYS / 'class/drm').glob('card[0-9]*')):
        if not re.fullmatch(r'card\d+', card.name):
            continue
        dev = card / 'device'
        if read(dev / 'vendor') != '0x1002':
            continue
        return {'device': card.name, 'activity': number(dev / 'gpu_busy_percent'),
                'frequencyMHz': gpu_frequency(read(dev / 'pp_dpm_sclk') or ''),
                'vramUsed': number(dev / 'mem_info_vram_used'),
                'vramTotal': number(dev / 'mem_info_vram_total'),
                'gttUsed': number(dev / 'mem_info_gtt_used'),
                'gttTotal': number(dev / 'mem_info_gtt_total')}
    return None


def temperatures():
    result = {'cpu': None, 'gpu': None}
    for node in sorted((SYS / 'class/hwmon').glob('hwmon[0-9]*')):
        name = read(node / 'name')
        if name not in ('k10temp', 'amdgpu'):
            continue
        target = 'cpu' if name == 'k10temp' else 'gpu'
        preferred = 'Tctl' if target == 'cpu' else 'edge'
        candidates = sorted(node.glob('temp*_input'))
        chosen = next((p for p in candidates if read(p.with_name(p.name.replace('_input', '_label'))) == preferred), None)
        if chosen is None:
            chosen = next((p for p in candidates if p.name == 'temp1_input'), None)
        if chosen:
            result[target] = number(chosen, 1000)
    return result


def network():
    text = read(PROC / 'net/dev') or ''
    candidates = []
    for line in text.splitlines()[2:]:
        if ':' not in line:
            continue
        name, raw = line.split(':', 1)
        name = name.strip()
        parts = raw.split()
        if name == 'lo' or len(parts) < 16:
            continue
        if read(SYS / 'class/net' / name / 'operstate') != 'up':
            continue
        try:
            candidates.append((name, int(parts[0]), int(parts[8])))
        except ValueError:
            pass
    candidates.sort(key=lambda x: (not (SYS / 'class/net' / x[0] / 'device').exists(), x[0]))
    return dict(zip(('interface', 'rx', 'tx'), candidates[0])) if candidates else None


def processes():
    result = []
    for node in PROC.glob('[0-9]*'):
        stat = read(node / 'stat')
        status = read(node / 'status')
        if not stat or not status:
            continue
        end = stat.rfind(')')
        if end < 0:
            continue
        fields = stat[end + 2:].split()
        try:
            ticks = int(fields[11]) + int(fields[12])
            start = int(fields[19])
            rss = int(re.search(r'^VmRSS:\s+(\d+) kB', status, re.M).group(1)) * 1024
            result.append({'pid': int(node.name), 'name': stat[stat.find('(')+1:end][:64],
                           'ticks': ticks, 'start': start, 'rss': rss})
        except (ValueError, IndexError, AttributeError):
            continue
    return result


def snapshot(include_gpu=False, include_disk=False, include_processes=False):
    # WHY: monotonic time makes rates independent of wall-clock changes.
    result = {'monotonic': time.monotonic(), 'cpu': cpu_ticks(read(PROC / 'stat') or ''),
              'load': (read(PROC / 'loadavg') or '').split()[:3],
              'memory': meminfo(read(PROC / 'meminfo') or ''),
              'psi': psi(read(PROC / 'pressure/memory') or ''),
              'zram': zram(read(SYS / 'block/zram0/mm_stat') or ''),
              'network': network()}
    vm = read(PROC / 'vmstat') or ''
    result['swapPages'] = {k: int(v) for k, v in re.findall(r'^(pswpin|pswpout)\s+(\d+)$', vm, re.M)}
    freqs = []
    for cpu in sorted((SYS / 'devices/system/cpu').glob('cpu[0-9]*'), key=lambda p: int(p.name[3:])):
        base = cpu / 'cpufreq'
        freqs.append({'cpu': cpu.name, 'currentMHz': number(base / 'scaling_cur_freq', 1000),
                      'minMHz': number(base / 'cpuinfo_min_freq', 1000),
                      'maxMHz': number(base / 'cpuinfo_max_freq', 1000)})
    result['frequencies'] = freqs
    if include_gpu:
        result['gpu'] = gpu()
        result['temperatures'] = temperatures()
    if include_disk:
        st = os.statvfs('/')
        total = st.f_blocks * st.f_frsize
        available = st.f_bavail * st.f_frsize
        result['disk'] = {'total': total, 'available': available,
                          'used': total - st.f_bfree * st.f_frsize,
                          'filesystem': next((m.split()[2] for m in (read(PROC / 'mounts') or '').splitlines()
                                                  if len(m.split()) >= 3 and m.split()[1] == '/'), None)}
    if include_processes:
        result['processes'] = processes()
        result['clockTicks'] = os.sysconf('SC_CLK_TCK')
    return result


if __name__ == '__main__':
    args = set(sys.argv[1:])
    try:
        print(json.dumps(snapshot('gpu' in args, 'disk' in args, 'processes' in args), separators=(',', ':')))
    except OSError as exc:
        print(json.dumps({'error': str(exc)}))
        sys.exit(1)
