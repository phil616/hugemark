"""Convert filesystem paths to browser URLs without Windows device prefixes."""
from pathlib import PureWindowsPath


def file_uri(path):
    # Keep extended paths for filesystem I/O; only normalize the URL boundary.
    if isinstance(path, PureWindowsPath):
        value = str(path)
        if value.startswith('\\\\?\\UNC\\'):
            path = PureWindowsPath('\\\\' + value[8:])
        elif value.startswith('\\\\?\\'):
            path = PureWindowsPath(value[4:])
    return path.as_uri()
