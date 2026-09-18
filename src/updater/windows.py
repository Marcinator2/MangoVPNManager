"""Windows process identity and cross-session installation locks."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path

from updater.release import UpdateError


def kernel():
    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    dll.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    dll.CreateMutexW.restype = wintypes.HANDLE
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.ReleaseMutex.argtypes = [wintypes.HANDLE]
    dll.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    dll.OpenProcess.restype = wintypes.HANDLE
    dll.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    dll.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    dll.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    dll.WaitForSingleObject.restype = wintypes.DWORD
    return dll


class InstallationLock:
    def __init__(self, root: Path, kind: str = "application") -> None:
        self.handle = None
        digest = hashlib.sha256(str(root.resolve()).casefold().encode("utf-8")).hexdigest()
        self.name = f"Global\\MangoVPNManager-{kind}-{digest}"

    def acquire(self):
        dll = kernel()
        ctypes.set_last_error(0)
        handle = dll.CreateMutexW(None, True, self.name)
        error = ctypes.get_last_error()
        if not handle or error == 183:
            if handle:
                dll.CloseHandle(handle)
            raise UpdateError("busy")
        self.handle = handle
        return self

    def close(self) -> None:
        if self.handle:
            dll = kernel()
            dll.ReleaseMutex(self.handle)
            dll.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, *args):
        self.close()


class ProcessIdentity:
    def __init__(self, pid: int, expected_path: Path, creation: int | None = None) -> None:
        dll = kernel()
        self.handle = dll.OpenProcess(0x100000 | 0x1000, False, pid)
        if not self.handle:
            raise UpdateError("process")
        try:
            times = [wintypes.FILETIME() for _ in range(4)]
            if not dll.GetProcessTimes(self.handle, *(ctypes.byref(t) for t in times)):
                raise UpdateError("process")
            self.creation = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            buffer = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(buffer))
            if not dll.QueryFullProcessImageNameW(self.handle, 0, buffer, ctypes.byref(length)):
                raise UpdateError("process")
            if Path(buffer.value).resolve() != expected_path.resolve() or (creation is not None and creation != self.creation):
                raise UpdateError("process")
        except BaseException:
            self.close()
            raise

    def wait(self, milliseconds: int = 60000) -> None:
        if kernel().WaitForSingleObject(self.handle, milliseconds) != 0:
            raise UpdateError("process")

    def exited(self) -> bool:
        result = kernel().WaitForSingleObject(self.handle, 0)
        if result not in (0, 258):
            raise UpdateError("process")
        return result == 0

    def close(self) -> None:
        if self.handle:
            kernel().CloseHandle(self.handle)
            self.handle = None


def current_identity(executable: Path) -> int:
    process = ProcessIdentity(os.getpid(), executable)
    try:
        return process.creation
    finally:
        process.close()
