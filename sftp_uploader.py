"""Blocking SFTP upload service; contains no Tkinter dependencies."""
from pathlib import Path
import socket
try:
    import paramiko
except ImportError:
    paramiko = None


def validate_settings(settings):
    if not settings.host or not settings.username or not settings.remote_path:
        raise ValueError("Host, username and remote path are required.")
    if not 1 <= settings.port <= 65535:
        raise ValueError("SFTP port must be between 1 and 65535.")


def upload_lists(settings, password, content, output_folder, progress=lambda text: None):
    validate_settings(settings)
    if paramiko is None:
        raise RuntimeError("Paramiko is not installed. Run: python -m pip install paramiko")
    transport = None
    sftp = None
    stage = "connecting"
    try:
        # Explicit timeouts also cover stalled SSH negotiation and authentication.
        connection = socket.create_connection((settings.host, settings.port), timeout=20)
        try:
            transport = paramiko.Transport(connection)
        except Exception:
            connection.close()
            raise
        transport.banner_timeout = 20
        transport.auth_timeout = 20
        transport.connect(username=settings.username, password=password)
        stage = "opening the SFTP session"
        sftp = paramiko.SFTPClient.from_transport(transport)
        sftp.get_channel().settimeout(30)
        out_dir = Path(output_folder).expanduser()
        out_dir.mkdir(parents=True, exist_ok=True)
        for file_name, names in content.items():
            local_file = out_dir / file_name
            stage = f"writing local file {local_file}"
            local_file.write_text("\n".join(names), encoding="utf-8")
            remote_file = settings.remote_path.rstrip("/") + "/" + file_name
            stage = f"uploading {remote_file}"
            sftp.put(str(local_file), remote_file)
            progress(f"Uploaded {file_name}")
    except Exception as exc:
        if isinstance(exc, paramiko.AuthenticationException):
            hint = "Authentication failed. Check the username/password and whether the server allows password login."
        elif isinstance(exc, socket.gaierror):
            hint = "Host could not be resolved. Check the host name and network connection."
        elif isinstance(exc, (TimeoutError, socket.timeout)):
            hint = "Connection timed out. Check the host, port, firewall and server availability."
        elif isinstance(exc, ConnectionRefusedError):
            hint = "Connection refused. Check the port and whether SSH/SFTP is running."
        elif isinstance(exc, PermissionError):
            hint = "Permission denied. Check local output and remote directory write permissions."
        else:
            hint = "Check the server, remote directory and SSH/SFTP configuration."
        # Avoid including arbitrary server error text that could echo credentials.
        raise RuntimeError(f"SFTP {settings.host}:{settings.port}: failed while {stage}. {hint} ({type(exc).__name__})") from exc
    finally:
        try:
            if sftp is not None:
                sftp.close()
        finally:
            if transport is not None:
                transport.close()
