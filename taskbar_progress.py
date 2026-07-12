"""
Windows taskbar progress via ITaskbarList3 (the same API File Explorer uses to
show green progress on its taskbar icon during copies).

Uses comtypes to talk to the shell COM object. Every call is wrapped so any
failure (non-Windows OS, old Windows, COM error, missing comtypes) degrades to
a silent no-op. Taskbar progress is a nicety, never a crash source.
"""
import sys

# ITaskbarList3 progress states
TBPF_NOPROGRESS = 0x0
TBPF_INDETERMINATE = 0x1
TBPF_NORMAL = 0x2
TBPF_ERROR = 0x4
TBPF_PAUSED = 0x8

_available = False
if sys.platform == "win32":
    try:
        import comtypes
        import comtypes.client
        from ctypes import HRESULT, c_ulonglong
        from ctypes.wintypes import HWND, INT, UINT
        from comtypes import GUID, IUnknown, COMMETHOD

        class ITaskbarList(IUnknown):
            _iid_ = GUID("{56FDF342-FD6D-11D0-958A-006097C9A090}")
            _methods_ = [
                COMMETHOD([], HRESULT, "HrInit"),
                COMMETHOD([], HRESULT, "AddTab", (["in"], HWND, "hwnd")),
                COMMETHOD([], HRESULT, "DeleteTab", (["in"], HWND, "hwnd")),
                COMMETHOD([], HRESULT, "ActivateTab", (["in"], HWND, "hwnd")),
                COMMETHOD([], HRESULT, "SetActiveAlt", (["in"], HWND, "hwnd")),
            ]

        class ITaskbarList2(ITaskbarList):
            _iid_ = GUID("{602D4995-B13A-429B-A66E-1935E44F4317}")
            _methods_ = [
                COMMETHOD([], HRESULT, "MarkFullscreenWindow",
                          (["in"], HWND, "hwnd"), (["in"], INT, "fFullscreen")),
            ]

        class ITaskbarList3(ITaskbarList2):
            _iid_ = GUID("{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}")
            _methods_ = [
                COMMETHOD([], HRESULT, "SetProgressValue",
                          (["in"], HWND, "hwnd"),
                          (["in"], c_ulonglong, "ullCompleted"),
                          (["in"], c_ulonglong, "ullTotal")),
                COMMETHOD([], HRESULT, "SetProgressState",
                          (["in"], HWND, "hwnd"), (["in"], UINT, "tbpFlags")),
                # Remaining ITaskbarList3 methods are not needed; vtable order
                # only matters up to the methods we call, and these two come first.
            ]

        _CLSID_TaskbarList = GUID("{56FDF344-FD6D-11D0-958A-006097C9A090}")
        _available = True
    except Exception:
        _available = False


class TaskbarProgress:
    """Progress reporter bound to one top-level window handle (HWND)."""

    def __init__(self, hwnd):
        self._hwnd = hwnd
        self._taskbar = None
        if not (_available and hwnd):
            return
        try:
            self._taskbar = comtypes.client.CreateObject(
                _CLSID_TaskbarList, interface=ITaskbarList3
            )
            self._taskbar.HrInit()
        except Exception:
            self._taskbar = None

    @property
    def active(self):
        return self._taskbar is not None

    def set_progress(self, completed, total):
        """Show green progress (like Explorer file copies). Values are clamped."""
        if not self._taskbar:
            return
        try:
            total = max(1, int(total))
            completed = max(0, min(int(completed), total))
            self._taskbar.SetProgressState(self._hwnd, TBPF_NORMAL)
            self._taskbar.SetProgressValue(self._hwnd, completed, total)
        except Exception:
            pass

    def set_error(self):
        """Turn the taskbar progress red (failure state)."""
        if not self._taskbar:
            return
        try:
            self._taskbar.SetProgressState(self._hwnd, TBPF_ERROR)
        except Exception:
            pass

    def set_paused(self):
        if not self._taskbar:
            return
        try:
            self._taskbar.SetProgressState(self._hwnd, TBPF_PAUSED)
        except Exception:
            pass

    def clear(self):
        """Remove the progress overlay from the taskbar icon."""
        if not self._taskbar:
            return
        try:
            self._taskbar.SetProgressState(self._hwnd, TBPF_NOPROGRESS)
        except Exception:
            pass
