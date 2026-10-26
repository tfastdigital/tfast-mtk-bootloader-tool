import ctypes
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

from . import config

class MetaUnlockEngine:
    def __init__(self):
        self.handoff_dir = config.HANDOFF_DIR
        self.runtime_dir = config.PY314_RUNTIME_DIR
        self.dll_path = self.runtime_dir / "python314.dll"
        # os.add_dll_directory returns a handle that must stay referenced;
        # if it is garbage-collected the directory is removed from the DLL
        # search path again, which makes the following PyDLL load fail.
        self._dll_dir_handles = []

    def is_available(self) -> bool:
        """Check if secure handoff engine and runtime are ready."""
        engine_pyd = self.handoff_dir / "engines" / "mtk_meta_protocol.pyd"
        return self.dll_path.exists() and engine_pyd.exists()

    def run_meta_unlock(self, com_port: Optional[str] = None) -> Tuple[bool, str]:
        """
        Execute MTK META Mode hardware bootloader unlock (NVRAM seccfg wipe).
        Uses python314 runtime harness to interface with mtk_meta_protocol.pyd.
        """
        if not self.is_available():
            return False, "META engine components missing from handoff_secure/ or py314_runtime/"

        try:
            for dll_dir in (self.runtime_dir, self.handoff_dir / "engines"):
                try:
                    self._dll_dir_handles.append(os.add_dll_directory(str(dll_dir)))
                except (AttributeError, OSError):
                    pass  # not on Windows, or already present
            py = ctypes.PyDLL(str(self.dll_path))

            zip_path = str(self.runtime_dir / "base_library.zip")
            lib_path = str(self.runtime_dir / "lib")
            engines_path = str(self.handoff_dir / "engines")

            py.Py_SetPythonHome.argtypes = [ctypes.c_wchar_p]
            py.Py_SetPythonHome.restype = None
            py.Py_SetPythonHome(str(self.runtime_dir))

            py.Py_SetPath.argtypes = [ctypes.c_wchar_p]
            py.Py_SetPath.restype = None
            py.Py_SetPath(f"{self.runtime_dir};{lib_path};{engines_path};{zip_path}")

            py.Py_Initialize.restype = None
            py.Py_Initialize.argtypes = []
            py.Py_Initialize()

            status_file = str(config.WORKSPACE_DIR / "meta_status.txt").replace('\\', '/')
            bl_core_dir = str(config.BASE_DIR / "bl_core").replace('\\', '/')
            os.makedirs(str(config.WORKSPACE_DIR), exist_ok=True)

            script = f"""
import sys
sys.path.insert(0, {repr(bl_core_dir)})
import meta_bridge
meta_bridge.run_meta_worker({repr(com_port)}, {repr(status_file)})
"""
            py.PyRun_SimpleStringFlags.restype = ctypes.c_int
            py.PyRun_SimpleStringFlags.argtypes = [ctypes.c_char_p, ctypes.c_void_p]
            code = py.PyRun_SimpleStringFlags(script.encode('utf-8'), None)

            # Read status file
            status_path = config.WORKSPACE_DIR / "meta_status.txt"
            if status_path.exists():
                content = status_path.read_text(encoding='utf-8').strip()
                status_path.unlink(missing_ok=True)
                if '|' in content:
                    c_str, m_str = content.split('|', 1)
                    return (c_str == '0', m_str)

            if code == 0:
                return True, "META Mode Unlock completed successfully"
            return False, f"META Engine exited with code {code}"
        except Exception as e:
            return False, f"META bridge execution error: {str(e)}"
