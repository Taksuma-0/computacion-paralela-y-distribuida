"""Mini "switch" (hub) Ethernet en el host para conectar varias VMs QEMU entre sí.

En Windows, `-netdev socket,mcast` no funciona y `listen/connect` es punto-a-punto.
Solución: cada VM usa `-netdev socket,connect=127.0.0.1:PUERTO` hacia este hub, que
acepta N conexiones y **reenvía cada trama a todas las demás** → un segmento L2
compartido (LAN interna VM↔VM) sin TAP/bridge ni privilegios de admin.

Protocolo de QEMU socket (modo stream/TCP): cada paquete va precedido por su longitud
en 4 bytes big-endian, seguido de la trama Ethernet cruda. El hub lee len+trama de cada
cliente y la retransmite (len+trama) a los otros.

Uso embebido:   Hub(port).start()  ...  hub.stop()
Uso standalone: python -m tui_gato.netbus [puerto]
"""

import socket
import struct
import sys
import threading


def _recvn(conn, n):
    data = b""
    while len(data) < n:
        try:
            chunk = conn.recv(n - len(data))
        except OSError:
            return None
        if not chunk:
            return None
        data += chunk
    return data


class Hub:
    def __init__(self, host="127.0.0.1", port=12340):
        self.host = host
        self.port = port
        self._srv = None
        self._clients = []
        self._lock = threading.Lock()
        self._stop = False
        self._thread = None

    def start(self):
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((self.host, self.port))
        self._srv.listen(8)
        self._srv.settimeout(0.5)
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        return self

    def _accept_loop(self):
        while not self._stop:
            try:
                conn, _ = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass
            with self._lock:
                self._clients.append(conn)
            threading.Thread(target=self._client_loop, args=(conn,), daemon=True).start()
        try:
            self._srv.close()
        except Exception:
            pass

    def _client_loop(self, conn):
        try:
            while not self._stop:
                hdr = _recvn(conn, 4)
                if hdr is None:
                    break
                (ln,) = struct.unpack(">I", hdr)
                if ln > 200000:            # trama implausible: desincronizado, cortar
                    break
                payload = _recvn(conn, ln) if ln else b""
                if payload is None:
                    break
                frame = hdr + payload
                with self._lock:
                    peers = [c for c in self._clients if c is not conn]
                for c in peers:
                    try:
                        c.sendall(frame)
                    except Exception:
                        pass
        except Exception:
            pass
        finally:
            with self._lock:
                if conn in self._clients:
                    self._clients.remove(conn)
            try:
                conn.close()
            except Exception:
                pass

    def num_clients(self):
        with self._lock:
            return len(self._clients)

    def stop(self):
        self._stop = True
        with self._lock:
            for c in self._clients:
                try:
                    c.close()
                except Exception:
                    pass
            self._clients = []
        try:
            if self._srv:
                self._srv.close()
        except Exception:
            pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 12340
    hub = Hub(port=port).start()
    print(f"Hub Ethernet en 127.0.0.1:{port} (Ctrl+C para salir)", flush=True)
    try:
        import time
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        hub.stop()


if __name__ == "__main__":
    main()
