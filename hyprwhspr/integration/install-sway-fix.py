#!/usr/bin/env python3
"""Install a pinned user-owned Hyprwhspr overlay; never edit pacman files.

WHY: both CLI and daemon must see the same detector. Keep the original package
and existing service/config intact; one removable systemd drop-in selects it.
CONTRACT: refuse unknown upstream sources and unmanaged destination files.
"""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile

SOURCE = Path('/usr/lib/hyprwhspr')
INJECTOR_SHA = 'e6bb5d4291d83cbd189d33bee1dc062b466d59b6a0fb1e1da170dba9b648ca29'
LAUNCHER_SHA = 'bfe5516566ac12b2f9958109f395d6504ef17dc3ac200eea8779f502a9896f22'
MARKER = '# HYPRWHSPR_SWAYFX_FOCUS_AND_PASTE_FIX_V1'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install():
    if digest(SOURCE/'lib/src/text_injector.py') != INJECTOR_SHA or digest(Path('/usr/bin/hyprwhspr')) != LAUNCHER_SHA:
        raise SystemExit('Upstream files changed: rebase/review the patch before installation.')
    home = Path.home()
    base = home/'.local/share/hyprwhspr-swayfx'
    destination = base/'1.52.1-sway-v1'
    link = home/'.local/bin/hyprwhspr'
    dropin = home/'.config/systemd/user/hyprwhspr.service.d/50-sway-focus-paste.conf'
    if (link.exists() or link.is_symlink()) and (not link.is_symlink() or link.readlink() != destination/'launcher'):
        raise SystemExit(f'Refusing unmanaged launcher: {link}')
    if dropin.exists() and MARKER not in dropin.read_text():
        raise SystemExit(f'Refusing unmanaged drop-in: {dropin}')
    base.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='prepare-', dir=base) as folder:
        stage = Path(folder)/'overlay'
        stage.mkdir()
        for child in SOURCE.iterdir():
            if child.name == 'lib':
                shutil.copytree(child, stage/'lib', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            else:
                (stage/child.name).symlink_to(child)
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i',
                        str(Path(__file__).with_name('sway-focus-paste.patch').resolve())],
                       cwd=stage, check=True, capture_output=True)
        launcher = Path('/usr/bin/hyprwhspr').read_text().replace(
            'PACKAGE_ROOT="/usr/lib/hyprwhspr"', f'PACKAGE_ROOT="{destination}"')
        # Fail closed after a package update instead of silently mixing versions.
        guard = f'''{MARKER}
upstream_digest=$(sha256sum /usr/lib/hyprwhspr/lib/src/text_injector.py)
if [[ "${{upstream_digest%% *}}" != "{INJECTOR_SHA}" ]]; then
    echo 'Hyprwhspr Sway overlay requires rebase after package update' >&2
    exit 1
fi
'''
        launcher = launcher.replace('#!/bin/bash\n', '#!/bin/bash\n'+guard, 1)
        (stage/'launcher').write_text(launcher)
        (stage/'launcher').chmod(0o755)
        if destination.exists():
            if digest(destination/'lib/src/text_injector.py') != digest(stage/'lib/src/text_injector.py') or digest(destination/'launcher') != digest(stage/'launcher'):
                raise SystemExit('Existing overlay differs; preserve it and choose a new reviewed version.')
        else:
            stage.rename(destination)
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.is_symlink():
        link.symlink_to(destination/'launcher')
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text(f'{MARKER}\n[Service]\nExecStart=\nExecStart="{destination}/launcher"\n')
    print(f'Installed {destination}; service restart is a separate controlled action.')


if __name__ == '__main__':
    install()
