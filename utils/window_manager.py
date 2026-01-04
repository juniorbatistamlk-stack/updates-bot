import ctypes
import sys
import os

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def set_console_icon(icon_path):
    """
    Sets the icon of the console window specifically for Windows.
    Changes both the small (title bar) and large (task switcher) icons.
    """
    if sys.platform != "win32":
        return

    try:
        # Resolve path using resource_path to support PyInstaller onefile
        icon_path = resource_path(icon_path)
        
        if not os.path.exists(icon_path):
            return

        # Windows API Constants
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1
        LR_LOADFROMFILE = 0x00000010
        IMAGE_ICON = 1
        
        # Load the icon
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        
        hwnd = kernel32.GetConsoleWindow()
        if not hwnd:
            return

        h_icon = user32.LoadImageW(
            None, 
            icon_path, 
            IMAGE_ICON, 
            0, 0, 
            LR_LOADFROMFILE
        )

        if h_icon:
            # Set small icon (Title bar) - 16x16
            user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_icon)
            # Set big icon (Taskbar / Alt-Tab) - 32x32
            user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_icon)
            
            # Also try to set the class icon for better compatibility
            try:
                GCL_HICON = -14
                GCL_HICONSM = -34
                user32.SetClassLongPtrW(hwnd, GCL_HICON, h_icon)
                user32.SetClassLongPtrW(hwnd, GCL_HICONSM, h_icon)
            except Exception:
                pass
            
    except Exception:
        # Debug: uncomment to see errors
        # print(f"Icon error: {e}")
        pass # Fail silently to not impact main bot execution

def set_console_title(title):
    """Sets the console window title."""
    if sys.platform == "win32":
        try:
            ctypes.windll.kernel32.SetConsoleTitleW(title)
        except Exception:
            pass
