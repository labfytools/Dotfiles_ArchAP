#!/usr/bin/env python3
"""TEST_ONLY Secret Service. No secrets/items/passwords exist in this fixture."""
import sys
from gi.repository import Gio, GLib

mode = sys.argv[1]
root = '/org/freedesktop/secrets'
collection = root + '/collection/Default_5fkeyring'
prompt = root + '/prompt/test'
locked = mode != 'ready'
xml = '''<node>
<interface name="org.freedesktop.Secret.Service">
 <method name="ReadAlias"><arg type="s" direction="in"/><arg type="o" direction="out"/></method>
 <method name="Unlock"><arg type="ao" direction="in"/><arg type="ao" direction="out"/><arg type="o" direction="out"/></method>
</interface>
<interface name="org.freedesktop.Secret.Collection"><property name="Locked" type="b" access="read"/></interface>
<interface name="org.freedesktop.Secret.Prompt">
 <method name="Prompt"><arg type="s" direction="in"/></method><method name="Dismiss"/>
 <signal name="Completed"><arg type="b"/><arg type="v"/></signal>
</interface></node>'''
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
bus.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus',
              'RequestName', GLib.Variant('(su)', ('org.freedesktop.secrets', 0)),
              GLib.VariantType.new('(u)'), Gio.DBusCallFlags.NONE, 2000, None)

def method(bus, sender, path, interface, name, args, invocation):
    global locked
    if name == 'ReadAlias':
        if mode == 'error':
            invocation.return_dbus_error('org.freedesktop.Secret.Error.Failed', 'TEST_ONLY_SENSITIVE_SENTINEL')
            return
        if mode == 'dbus-timeout': return  # deliberately leave request unanswered
        alias = args.unpack()[0]
        value = collection if alias == 'default' else '/'
        if mode == 'missing': value = '/'
        if mode == 'different' and alias == 'default': value = root + '/collection/other'
        if mode == 'login-different' and alias == 'login': value = root + '/collection/login'
        invocation.return_value(GLib.Variant('(o)', (value,)))
    elif name == 'Unlock':
        print('UNLOCK', flush=True)
        if mode == 'immediate':
            locked = False
            invocation.return_value(GLib.Variant('(aoo)', ([collection], '/')))
        else: invocation.return_value(GLib.Variant('(aoo)', ([], prompt)))
    elif name == 'Prompt':
        print('PROMPT', flush=True)
        invocation.return_value(GLib.Variant('()', ()))
        def complete():
            global locked
            if mode not in ('still-locked', 'wrong-password', 'cancel'): locked = False
            bus.emit_signal(sender, prompt, interface, 'Completed',
                GLib.Variant('(bv)', (mode == 'cancel', GLib.Variant('ao', [collection]))))
            return False
        if mode not in ('timeout', 'wrong-password'):
            GLib.timeout_add(400 if mode == 'slow' else 10, complete)
    elif name == 'Dismiss':
        print('DISMISS', flush=True)
        invocation.return_value(GLib.Variant('()', ()))

def prop(*_): return GLib.Variant('b', locked)

node = Gio.DBusNodeInfo.new_for_xml(xml)
for path, iface in ((root, 0), (collection, 1), (prompt, 2)):
    bus.register_object(path, node.interfaces[iface], method, prop, None)
print('READY', flush=True)
GLib.MainLoop().run()
