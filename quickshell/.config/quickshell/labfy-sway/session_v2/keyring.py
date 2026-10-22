"""Secret Service readiness, without ever opening a secret session or reading items.

WHY: daemon existence and a vanished prompt do not prove collection readiness.
CONTRACT: default must be the audited collection; an existing login alias must
agree. Missing login is supported (manual unlock), never proof of PAM success.
INVARIANT: no cached readiness, passwords, item metadata or free-form D-Bus errors
are persisted/logged. A private connection owns and dismisses only its prompt.
"""
from contextlib import contextmanager
import math
import signal
import time
from .errors import Failure, require
from .storage import lock, private_dir

BUS = 'org.freedesktop.secrets'
ROOT = '/org/freedesktop/secrets'
SERVICE = 'org.freedesktop.Secret.Service'
COLLECTION = 'org.freedesktop.Secret.Collection'
PROMPT = 'org.freedesktop.Secret.Prompt'
EXPECTED = ROOT + '/collection/Default_5fkeyring'


def result(state, reason):
    return {'state': 'KEYRING_' + state, 'reason': reason}


class Secrets:
    def __init__(self, timeout=8):
        # Lazy import keeps existing backend diagnostics usable without PyGObject.
        from gi.repository import Gio, GLib, GLibUnix
        self.Gio, self.GLib, self.GLibUnix = Gio, GLib, GLibUnix
        self.deadline = time.monotonic() + timeout
        address = Gio.dbus_address_get_for_bus_sync(Gio.BusType.SESSION, None)
        # Bound connection/authentication too, not only subsequent RPC calls.
        loop, cancellation, opened = GLib.MainLoop(), Gio.Cancellable(), []
        expired = []
        def connected(_source, response, _data):
            try:
                bus = Gio.DBusConnection.new_for_address_finish(response)
                if expired: bus.close_sync(None)
                else: opened.append(bus)
            except GLib.Error: pass
            loop.quit()
        def expire():
            expired.append(True)
            cancellation.cancel()
            loop.quit()
            return False
        timer = GLib.timeout_add(2000, expire)
        try:
            Gio.DBusConnection.new_for_address(address,
                Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT |
                Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None,
                cancellation, connected, None)
            loop.run()
        finally:
            if GLib.MainContext.default().find_source_by_id(timer): GLib.source_remove(timer)
        require(not expired, 'KEYRING_TIMEOUT')
        require(opened, 'KEYRING_BUS_UNAVAILABLE')
        self.bus = opened[0]
        self.owner = None
        try:
            # Calls after activation are pinned to a unique owner. A replacement
            # service must never inherit readiness from this connection.
            try: self.owner = self.get_owner()
            except GLib.Error:
                self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                          'org.freedesktop.DBus', 'StartServiceByName', '(su)', (BUS, 0), '(u)')
                self.owner = self.get_owner()
        except BaseException:
            self.close()
            raise

    def call(self, destination, path, interface, method, signature, args, reply):
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, 'KEYRING_TIMEOUT')
        return self.bus.call_sync(destination, path, interface, method,
            self.GLib.Variant(signature, args) if signature else None,
            self.GLib.VariantType.new(reply), self.Gio.DBusCallFlags.NO_AUTO_START,
            max(1, min(2000, math.ceil(remaining * 1000))), None).unpack()

    def get_owner(self):
        return self.call('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'GetNameOwner', '(s)', (BUS,), '(s)')[0]

    def alias(self, name):
        return self.call(self.owner, ROOT, SERVICE, 'ReadAlias', '(s)', (name,), '(o)')[0]

    def inspect(self):
        require(self.get_owner() == self.owner, 'KEYRING_OWNER_CHANGED')
        collection = self.alias('default')
        require(collection != '/', 'KEYRING_DEFAULT_MISSING')
        require(collection == EXPECTED, 'KEYRING_COLLECTION_MISMATCH')
        login = self.alias('login')
        require(login in ('/', collection), 'KEYRING_LOGIN_MISMATCH')
        value = self.call(self.owner, collection, 'org.freedesktop.DBus.Properties',
            'Get', '(ss)', (COLLECTION, 'Locked'), '(v)')[0]
        require(type(value) is bool, 'KEYRING_INVALID_LOCKED')
        require(self.get_owner() == self.owner, 'KEYRING_OWNER_CHANGED')
        return value

    def unlock(self, timeout=90):
        self.deadline = time.monotonic() + timeout
        unlocked, prompt = self.call(self.owner, ROOT, SERVICE, 'Unlock', '(ao)', ([EXPECTED],), '(aoo)')
        if prompt == '/': return
        loop = self.GLib.MainLoop()
        completed = []
        def receive(_bus, _sender, _path, _iface, _signal, parameters):
            # Do not retain/inspect the operation-specific variant payload.
            completed.append(parameters.get_child_value(0).get_boolean())
            loop.quit()
        subscription = self.bus.signal_subscribe(self.owner, PROMPT, 'Completed', prompt,
            None, self.Gio.DBusSignalFlags.NONE, receive)
        timer = self.GLib.timeout_add(max(1, math.ceil((self.deadline - time.monotonic()) * 1000)),
                                     lambda: (loop.quit(), False)[1])
        def cancel():
            completed.append(True)
            loop.quit()
            return False
        # GLib owns the prompt wait: Python signal handlers alone are not
        # dispatched while its native loop is idle. Termination must wake it.
        termination = self.GLibUnix.signal_add(self.GLib.PRIORITY_DEFAULT, signal.SIGTERM, cancel)
        try:
            # Empty window-id is the portable unparented prompt. QuickShell
            # releases its exclusive keyboard surface before this call.
            self.call(self.owner, prompt, PROMPT, 'Prompt', '(s)', ('',), '()')
            if not completed: loop.run()
            require(completed, 'KEYRING_TIMEOUT')
            require(completed[0] is False, 'KEYRING_CANCELLED')
        finally:
            for source in (timer, termination):
                if self.GLib.MainContext.default().find_source_by_id(source):
                    self.GLib.source_remove(source)
            self.bus.signal_unsubscribe(subscription)
            # Best effort cleanup also runs on timeout/termination. Closing the
            # private connection invalidates outstanding client-owned prompts.
            try:
                self.deadline = time.monotonic() + 1
                self.call(self.owner, prompt, PROMPT, 'Dismiss', None, (), '()')
            except (Failure, self.GLib.Error): pass

    def close(self):
        self.bus.close_sync(None)


def check(unlock=False, factory=Secrets, timeout=90):
    connection = None
    try:
        connection = factory()
        if not connection.inspect(): return result('READY', 'KEYRING_UNLOCKED')
        if not unlock: return result('LOCKED', 'KEYRING_LOCKED')
        connection.unlock(timeout)
        connection.deadline = time.monotonic() + 8
        if connection.inspect(): return result('LOCKED', 'KEYRING_STILL_LOCKED')
        return result('READY', 'KEYRING_UNLOCKED')
    except Failure as exc:
        return result('CANCELLED' if exc.code == 'KEYRING_CANCELLED' else 'UNAVAILABLE', exc.code)
    except ImportError:
        return result('UNAVAILABLE', 'KEYRING_DEPENDENCY_MISSING')
    except Exception:
        # Never expose remote error text; it may contain user-supplied material.
        return result('UNAVAILABLE', 'KEYRING_DBUS_ERROR')
    finally:
        if connection is not None:
            try: connection.close()
            except Exception: pass


@contextmanager
def admission(runtime):
    """Serialize unlock and CLI restoration across processes/QuickShell restarts.

    CONTRACT: acquire before the existing transaction lock, hold through apply.
    No boolean, token or file survives as authorization for a future apply.
    New-session acknowledgement uses only the existing transaction lock.
    """
    with lock(private_dir(runtime / 'session-v2'), 'keyring.lock'):
        yield


def command(runtime, unlock=False):
    try:
        with admission(runtime):
            # An executor/guard predating this gate can still own the old lock.
            # Check it before any Unlock; don't hold it during user interaction.
            with lock(private_dir(runtime / 'session-v2')): pass
            return check(unlock)
    except KeyboardInterrupt:
        return result('CANCELLED', 'KEYRING_CANCELLED')
    except Failure as exc:
        if exc.code == 'TRANSACTION_BUSY': return result('UNLOCKING', 'KEYRING_OR_RESTORE_BUSY')
        raise


def require_ready():
    value = check()
    require(value['state'] == 'KEYRING_READY', value['reason'])
