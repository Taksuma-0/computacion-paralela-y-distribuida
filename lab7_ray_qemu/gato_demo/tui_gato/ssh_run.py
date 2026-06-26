"""SSH por LLAVE (paramiko) hacia la VM Debian (usuario `ray`):
- ssh_ready: ¿autentica con la llave?
- run_command: ejecutar y esperar (ray start, ray stop...).
- stream_command: ejecutar y transmitir stdout línea a línea (entrenamiento en vivo).
- sftp_put / sftp_get: subir el script, bajar el modelo.

El acceso es SIN contraseña: la pública de `ray_cluster` se inyecta en los qcow2 con
preparar_acceso_ray.ps1 (offline, vía libguestfs), igual que en el clúster Alpine."""

import logging
import os
import time

import paramiko

# paramiko loguea a stderr intentos fallidos mientras la VM arranca: silenciar.
logging.getLogger("paramiko").setLevel(logging.CRITICAL)

# Llave propia (override con RAY_CLUSTER_KEY).
KEY_PATH = os.environ.get("RAY_CLUSTER_KEY",
                          os.path.join(os.path.expanduser("~"), ".ssh", "ray_cluster"))


def _connect(host, port, user, timeout=12):
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(host, port=port, username=user, key_filename=KEY_PATH,
                timeout=timeout, banner_timeout=timeout, auth_timeout=timeout,
                look_for_keys=False, allow_agent=False)
    return cli


def ssh_ready(host, port, user, timeout=6) -> bool:
    try:
        cli = _connect(host, port, user, timeout=timeout)
        cli.close()
        return True
    except Exception:
        return False


def run_command(host, port, user, command, timeout=120):
    """Ejecuta un comando y espera. Devuelve (exit_code, stdout, stderr)."""
    cli = _connect(host, port, user)
    try:
        stdin, stdout, stderr = cli.exec_command(command, timeout=timeout)
        code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        return code, out, err
    finally:
        cli.close()


def stream_command(host, port, user, command, on_line, stop_flag):
    """Ejecuta `command` y entrega su stdout (y stderr) línea a línea a on_line(str).
    Corta si stop_flag() devuelve True. Devuelve el exit code (o None)."""
    cli = _connect(host, port, user)
    code = None
    try:
        chan = cli.get_transport().open_session()
        chan.set_combine_stderr(True)
        chan.settimeout(0.0)
        chan.exec_command(command)
        buf = b""
        while not stop_flag():
            if chan.recv_ready():
                data = chan.recv(8192)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    raw, buf = buf.split(b"\n", 1)
                    line = raw.decode("utf-8", "replace").rstrip()
                    if line:
                        on_line(line)
            elif chan.exit_status_ready() and not chan.recv_ready():
                break
            else:
                time.sleep(0.05)
        if buf:
            line = buf.decode("utf-8", "replace").rstrip()
            if line:
                on_line(line)
        try:
            code = chan.recv_exit_status()
        except Exception:
            code = None
    finally:
        cli.close()
    return code


def sftp_put(host, port, user, local_path, remote_path):
    cli = _connect(host, port, user)
    try:
        sftp = cli.open_sftp()
        try:
            rdir = remote_path.rsplit("/", 1)[0]
            if rdir:
                _mkdirs(sftp, rdir)
            sftp.put(local_path, remote_path)
        finally:
            sftp.close()
    finally:
        cli.close()


def sftp_get(host, port, user, remote_path, local_path):
    cli = _connect(host, port, user)
    try:
        sftp = cli.open_sftp()
        try:
            sftp.get(remote_path, local_path)
        finally:
            sftp.close()
    finally:
        cli.close()


def _mkdirs(sftp, path):
    parts = path.strip("/").split("/")
    cur = ""
    for p in parts:
        cur += "/" + p
        try:
            sftp.stat(cur)
        except IOError:
            try:
                sftp.mkdir(cur)
            except Exception:
                pass
