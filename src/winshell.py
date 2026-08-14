"""Integración con Windows: instalar, registrar las extensiones y desinstalar.

Todo se escribe en HKCU, de modo que nunca se piden privilegios de
administrador ni se altera la configuración de otros usuarios.

Windows 10 y 11 no permiten que un programa se designe a si mismo como
predeterminado: aquí solo se registra la aplicación como candidata y el usuario
la elige desde "Abrir con".
"""

import ctypes
import os
import shutil
import subprocess
import sys
import winreg
from pathlib import Path

APP_NAME = "Visor MD"
APP_ID = "VisorMD"
VERSION = "1.0.0"
PUBLISHER = "Visor MD"
EXE_NAME = "VisorMD.exe"
INSTALL_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Programs" / APP_ID
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{APP_ID}"
START_MENU = (Path(os.environ.get("APPDATA", Path.home())) / "Microsoft" / "Windows" /
              "Start Menu" / "Programs" / f"{APP_NAME}.lnk")

# Rutas absolutas: invocar por nombre permitiria sustituir el ejecutable
# colocando otro con el mismo nombre en el directorio de trabajo.
SYSTEM32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
POWERSHELL = SYSTEM32 / "WindowsPowerShell" / "v1.0" / "powershell.exe"
CMD = SYSTEM32 / "cmd.exe"

CREATE_NO_WINDOW = 0x08000000

EXTENSIONS = {
    ".md": f"{APP_ID}.md",
    ".markdown": f"{APP_ID}.md",
    ".mdown": f"{APP_ID}.md",
    ".mkd": f"{APP_ID}.md",
    ".txt": f"{APP_ID}.txt",
}
PROGIDS = {f"{APP_ID}.md": "Documento Markdown", f"{APP_ID}.txt": "Documento de texto"}


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def current_exe() -> Path:
    return Path(sys.executable if is_frozen() else sys.argv[0]).resolve()


def installed_exe() -> Path:
    return INSTALL_DIR / EXE_NAME


def is_installed() -> bool:
    return installed_exe().exists()


def is_registered() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            rf"Software\Classes\{APP_ID}.md\shell\open\command"):
            return True
    except OSError:
        return False


def _set(root: int, path: str, value: str, name: str = "") -> None:
    with winreg.CreateKey(root, path) as k:
        winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)


def _delete_tree(root: int, path: str) -> None:
    try:
        with winreg.OpenKey(root, path) as k:
            subkeys = [winreg.EnumKey(k, i) for i in range(winreg.QueryInfoKey(k)[0])]
        for sub in subkeys:
            _delete_tree(root, f"{path}\\{sub}")
        winreg.DeleteKey(root, path)
    except OSError:
        pass


def _refresh_explorer() -> None:
    """Avisar al Explorador que cambiaron las asociaciones (SHCNE_ASSOCCHANGED)."""
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)


def register(exe: Path) -> dict:
    """Registrar los ProgID y añadir la aplicación a "Abrir con"."""
    if not is_frozen() and exe.suffix.lower() != ".exe":
        return {"ok": False, "error": "El registro solo funciona sobre el ejecutable compilado."}
    hk = winreg.HKEY_CURRENT_USER
    cmd = f'"{exe}" "%1"'
    for progid, label in PROGIDS.items():
        _set(hk, rf"Software\Classes\{progid}", label)
        _set(hk, rf"Software\Classes\{progid}\DefaultIcon", f"{exe},0")
        _set(hk, rf"Software\Classes\{progid}\shell\open", "Abrir con Visor MD")
        _set(hk, rf"Software\Classes\{progid}\shell\open\command", cmd)
    for ext, progid in EXTENSIONS.items():
        with winreg.CreateKey(hk, rf"Software\Classes\{ext}\OpenWithProgids") as k:
            winreg.SetValueEx(k, progid, 0, winreg.REG_NONE, b"")
    app = rf"Software\Classes\Applications\{exe.name}"
    _set(hk, rf"{app}\shell\open\command", cmd)
    _set(hk, rf"{app}\DefaultIcon", f"{exe},0")
    _set(hk, app, APP_NAME, "FriendlyAppName")
    with winreg.CreateKey(hk, rf"{app}\SupportedTypes") as k:
        for ext in EXTENSIONS:
            winreg.SetValueEx(k, ext, 0, winreg.REG_SZ, "")
    _refresh_explorer()
    return {"ok": True, "exe": str(exe)}


def _create_shortcut(exe: Path) -> None:
    START_MENU.parent.mkdir(parents=True, exist_ok=True)
    quote = lambda p: str(p).replace("'", "''")  # noqa: E731
    script = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{quote(START_MENU)}');"
              f"$s.TargetPath='{quote(exe)}';$s.WorkingDirectory='{quote(exe.parent)}';"
              f"$s.Description='{APP_NAME}';$s.Save()")
    subprocess.run([str(POWERSHELL), "-NoProfile", "-NonInteractive", "-Command", script],
                   creationflags=CREATE_NO_WINDOW, check=False)


def install() -> dict:
    """Copiar la aplicación a la carpeta del usuario y registrarla en Windows."""
    if not is_frozen():
        return {"ok": False, "error": "La instalación solo funciona sobre el ejecutable "
                                      "compilado. En desarrollo se usa --register."}
    source_dir = current_exe().parent
    target = installed_exe()
    try:
        if source_dir != INSTALL_DIR:
            shutil.copytree(source_dir, INSTALL_DIR, dirs_exist_ok=True)
        INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return {"ok": False, "error": f"No se pudo copiar a {INSTALL_DIR}: {e}. "
                                      "Si ya está instalado, cerrar esa ventana primero."}
    res = register(target)
    if not res.get("ok"):
        return res
    _create_shortcut(target)
    hk = winreg.HKEY_CURRENT_USER
    _set(hk, UNINSTALL_KEY, APP_NAME, "DisplayName")
    _set(hk, UNINSTALL_KEY, VERSION, "DisplayVersion")
    _set(hk, UNINSTALL_KEY, PUBLISHER, "Publisher")
    _set(hk, UNINSTALL_KEY, str(target), "DisplayIcon")
    _set(hk, UNINSTALL_KEY, str(INSTALL_DIR), "InstallLocation")
    _set(hk, UNINSTALL_KEY, f'"{target}" --uninstall', "UninstallString")
    with winreg.CreateKey(hk, UNINSTALL_KEY) as k:
        winreg.SetValueEx(k, "NoModify", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(k, "NoRepair", 0, winreg.REG_DWORD, 1)
    return {"ok": True, "dir": str(INSTALL_DIR), "exe": str(target)}


def uninstall(confirm: bool = False) -> dict:
    """Revertir el registro y eliminar el acceso directo y la carpeta de instalación."""
    if confirm:
        answer = ctypes.windll.user32.MessageBoxW(
            0, f"¿Desinstalar {APP_NAME}?\n\nSe quitarán las asociaciones de archivo "
               f"y la carpeta:\n{INSTALL_DIR}\n\nLos documentos no se modifican.",
            APP_NAME, 0x00000004 | 0x00000020)
        if answer != 6:  # IDYES
            return {"ok": False, "cancelled": True}
    hk = winreg.HKEY_CURRENT_USER
    for progid in PROGIDS:
        _delete_tree(hk, rf"Software\Classes\{progid}")
    for ext, progid in EXTENSIONS.items():
        try:
            with winreg.OpenKey(hk, rf"Software\Classes\{ext}\OpenWithProgids", 0,
                                winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, progid)
        except OSError:
            pass
    _delete_tree(hk, rf"Software\Classes\Applications\{EXE_NAME}")
    _delete_tree(hk, UNINSTALL_KEY)
    START_MENU.unlink(missing_ok=True)
    _refresh_explorer()
    if INSTALL_DIR.exists():
        # Un ejecutable en curso no puede borrarse a si mismo: lo hace un
        # proceso diferido.
        subprocess.Popen(
            f'"{CMD}" /c "{SYSTEM32 / "timeout.exe"}" /t 2 /nobreak >nul '
            f'& rmdir /s /q "{INSTALL_DIR}"',
            creationflags=CREATE_NO_WINDOW)
    if confirm:
        ctypes.windll.user32.MessageBoxW(0, f"{APP_NAME} se desinstaló.", APP_NAME, 0x00000040)
    return {"ok": True}
