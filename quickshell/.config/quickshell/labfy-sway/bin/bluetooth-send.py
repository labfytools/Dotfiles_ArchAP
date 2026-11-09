#!/usr/bin/python
"""Probe Object Push support, or hand file selection and transfer to Blueman."""
import os
import re
import shutil
import subprocess
import sys
from urllib.parse import urlsplit, unquote


def select_files():
    """Use the configured XDG portal (termfilechooser/Yazi on this desktop)."""
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    from gi.repository import GLib
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    loop = GLib.MainLoop()
    result = []
    failure = []
    token = 'bluetooth_' + str(os.getpid())
    # CONTRACT: subscribe before OpenFile so a fast cancellation cannot be lost.
    request_path = '/org/freedesktop/portal/desktop/request/' + bus.get_unique_name()[1:].replace('.', '_') + '/' + token

    def response(code, values):
        if int(code) == 0:
            result.extend(str(uri) for uri in values.get('uris', []))
        elif int(code) != 1:
            failure.append('Le sélecteur de fichiers XDG a échoué')
        loop.quit()

    match = bus.add_signal_receiver(response, signal_name='Response', dbus_interface='org.freedesktop.portal.Request', path=request_path)
    try:
        portal = bus.get_object('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop')
        portal.OpenFile('', 'Envoyer un fichier par Bluetooth',
                        dbus.Dictionary({'handle_token': token, 'multiple': dbus.Boolean(False), 'directory': dbus.Boolean(False)}, signature='sv'),
                        dbus_interface='org.freedesktop.portal.FileChooser')
        loop.run()
    finally:
        match.remove()
    if failure:
        raise RuntimeError(failure[0])
    files = []
    for uri in result:
        parsed = urlsplit(uri)
        if parsed.scheme != 'file' or parsed.netloc not in ('', 'localhost'):
            raise ValueError('Sélectionner un fichier local')
        path = unquote(parsed.path)
        if not os.path.isfile(path):
            raise ValueError('Le fichier sélectionné est indisponible')
        files.append(path)
    return files


def main():
    mode, adapter, address = sys.argv[1:]
    if mode not in ('probe', 'send') or not re.fullmatch(r'hci[0-9]+', adapter) or not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', address):
        raise ValueError('Adresse Bluetooth invalide')
    import dbus
    objects = dbus.SystemBus().get_object('org.bluez', '/').GetManagedObjects(dbus_interface='org.freedesktop.DBus.ObjectManager')
    path = next((p for p, v in objects.items() if 'org.bluez.Adapter1' in v and str(p).rsplit('/', 1)[-1] == adapter), None)
    device = next((v['org.bluez.Device1'] for p, v in objects.items() if 'org.bluez.Device1' in v and str(v['org.bluez.Device1'].get('Adapter')) == path and str(v['org.bluez.Device1'].get('Address', '')).upper() == address.upper()), None)
    if device is None or '00001105-0000-1000-8000-00805f9b34fb' not in [str(u).lower() for u in device.get('UUIDs', [])]:
        print('unsupported')
        return 0
    if not shutil.which('blueman-sendto') or not os.path.isfile('/usr/lib/systemd/user/obex.service'):
        print('Transfert indisponible : installer les dépendances avec sudo pacman -S blueman bluez-obex')
        return 1
    if mode == 'probe':
        print('supported')
        return 0
    files = select_files()
    if not files:
        return 0  # Cancellation must never launch Blueman or a transfer.
    # CONTRACT: explicit local absolute paths bypass Blueman's GTK chooser.
    # Blueman owns progress/result; never pass --delete or connect generically.
    return subprocess.call(['blueman-sendto', '--source', adapter, '--device', address, '--', *files])



if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as error:
        print('Impossible de lancer l’envoi Bluetooth : ' + str(error))
        sys.exit(1)
