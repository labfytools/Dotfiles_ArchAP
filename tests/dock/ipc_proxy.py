"""Test-only disconnectable proxy; targets only a fixture-owned Sway socket."""
import select
import socket
import threading


class IpcProxy:
    def __init__(self, path, target):
        self.target = target
        self.socket = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.socket.bind(str(path)); self.socket.listen(8); self.socket.settimeout(.2)
        self.stopped = threading.Event()
        self.lock = threading.Lock()
        self.connections = set()
        self.thread = threading.Thread(target=self.accept,daemon=True)
        self.thread.start()

    def accept(self):
        while not self.stopped.is_set():
            try: client,_ = self.socket.accept()
            except socket.timeout: continue
            except OSError: break
            upstream=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
            upstream.settimeout(2)
            try: upstream.connect(self.target)
            except OSError: client.close(); upstream.close(); continue
            with self.lock:
                if len(self.connections)>=16:
                    client.close(); upstream.close(); continue
                self.connections.add(client); self.connections.add(upstream)
            threading.Thread(target=self.forward,args=(client,upstream),daemon=True).start()

    def forward(self, client, upstream):
        try:
            while not self.stopped.is_set():
                ready,_,_=select.select([client,upstream],[],[],.2)
                for source in ready:
                    data=source.recv(65536)
                    if not data: return
                    (upstream if source is client else client).sendall(data)
        except (OSError,ValueError): pass
        finally:
            with self.lock:
                self.connections.discard(client); self.connections.discard(upstream)
            client.close(); upstream.close()

    def disconnect(self):
        with self.lock:
            for connection in self.connections:
                try: connection.shutdown(socket.SHUT_RDWR)
                except OSError: pass

    def close(self):
        self.stopped.set(); self.disconnect(); self.socket.close(); self.thread.join(2)
