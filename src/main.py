"""Visor MD: visor y editor de Markdown para Windows.

Uso:
    VisorMD.exe [archivo.md]              Abre el archivo; si ya hay una
                                           ventana abierta, se agrega como
                                           pestaña nueva en lugar de abrir otra.
    VisorMD.exe --new-window [archivo.md] Fuerza una ventana nueva, sin
                                           reutilizar ninguna existente.
    VisorMD.exe --uninstall               Invocado por la entrada de
                                           desinstalación de Windows.
    VisorMD.exe --register                Registra las asociaciones de
                                           archivo sin instalar.

Todas las ventanas viven en un mismo proceso: abrir una es instantáneo,
comparten los ajustes en memoria y mover una pestaña de una a otra no
necesita comunicación entre procesos.

Copyright (C) 2026 Angel David Durán Erazo

Este programa es software libre: puede redistribuirse o modificarse bajo
los términos de la GNU General Public License, versión 3, publicada por la
Free Software Foundation. Ver LICENSE para el texto completo.
"""

import base64
import ctypes
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

import webview

import winshell

APP_NAME = "Visor MD"
VERSION = "1.0.0"
DARK_BG = "#061401"
CONFIG = Path(os.environ.get("APPDATA", Path.home())) / "VisorMD" / "settings.json"
WEBVIEW_PROFILE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "VisorMD" / "WebView2"
DEFAULTS = {"theme": "dark", "split": False, "toc": False,
            "width": 1100, "height": 780, "font_size": 16, "recent": [],
            # Configuración avanzada. Los valores estrictos son el punto de
            # partida; se aflojan desde el menú para trabajar con fuentes
            # propias. Ver docs/frontera-de-seguridad.md.
            "contain_images": True, "block_remote": True,
            "trusted_dirs": [], "max_diagrams": 50}

IMAGE_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml",
    ".bmp": "image/bmp", ".avif": "image/avif", ".ico": "image/x-icon",
}
MAX_IMAGE_BYTES = 20 * 1024 * 1024

# Puerto de instancia única, en loopback. Solo un proceso puede enlazarlo:
# ese enlace hace de mutex y de canal para recibir rutas de otras instancias.
SINGLETON_PORT = 51900 + (zlib.crc32(os.environ.get("USERNAME", "user").encode()) % 400)

# El socket del servidor debe sobrevivir mientras dure el proceso: si se
# recolecta, el puerto se libera y deja de haber instancia principal.
_singleton_socket: "socket.socket | None" = None
_app: "App | None" = None

# Rutas que llegaron de otras instancias antes de que la interfaz estuviera
# lista. Abrir varios archivos a la vez desde el Explorador lanza un proceso
# por archivo, y todos llegan mucho antes de que la ventana termine de cargar.
_pending_paths: list[str] = []
_pending_lock = threading.Lock()


def resource(*parts) -> Path:
    """Resolver la ruta de un recurso desde el código fuente o desde el ejecutable."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base.joinpath(*parts)


def read_settings() -> dict:
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(CONFIG.read_text("utf-8")))
    except Exception:
        pass
    return data


def write_settings(data: dict) -> None:
    try:
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(data, indent=2), "utf-8")
    except Exception:
        pass


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def cursor_position() -> tuple[int, int]:
    """Posición del puntero en píxeles físicos de pantalla."""
    point = _Point()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def clear_web_cache() -> None:
    """Vaciar la caché HTTP del perfil de WebView2 al arrancar.

    La interfaz se sirve desde un servidor local, así que el navegador la
    guarda en caché y tras actualizar la aplicación seguiría mostrando la
    versión anterior. El resto del perfil se conserva: es lo que hace que el
    arranque sea rápido.
    """
    cache = WEBVIEW_PROFILE / "EBWebView" / "Default" / "Cache"
    try:
        shutil.rmtree(cache)
    except OSError:
        pass


def restore_resize_border(hwnd: int) -> None:
    """Devolver los bordes de redimensionado a una ventana sin marco.

    Sin marco, Windows la trata como emergente: no se puede redimensionar
    arrastrando los bordes ni acoplar a los lados. WS_THICKFRAME recupera las
    dos cosas sin traer de vuelta la barra de título.
    """
    if not hwnd:
        return
    user32 = ctypes.windll.user32
    user32.GetWindowLongPtrW.restype = ctypes.c_longlong
    user32.SetWindowLongPtrW.restype = ctypes.c_longlong
    style = user32.GetWindowLongPtrW(hwnd, -16)  # GWL_STYLE
    nuevo = style | 0x00040000 | 0x00010000 | 0x00020000  # THICKFRAME, MAX, MINBOX
    if nuevo == style:
        return
    user32.SetWindowLongPtrW(hwnd, -16, ctypes.c_longlong(nuevo))
    user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0002 | 0x0001 | 0x0004)


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MINMAXINFO(ctypes.Structure):
    _fields_ = [("ptReserved", _POINT), ("ptMaxSize", _POINT),
                ("ptMaxPosition", _POINT), ("ptMinTrackSize", _POINT),
                ("ptMaxTrackSize", _POINT)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT),
                ("rcWork", _RECT), ("dwFlags", ctypes.c_ulong)]


def monitor_work_area(hwnd: int) -> tuple[_RECT, _RECT] | None:
    """Área del monitor de la ventana: la completa y la libre de barras."""
    user32 = ctypes.windll.user32
    monitor = user32.MonitorFromWindow(ctypes.c_void_p(hwnd), 2)  # NEAREST
    if not monitor:
        return None
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    if not user32.GetMonitorInfoW(ctypes.c_void_p(monitor), ctypes.byref(info)):
        return None
    return info.rcMonitor, info.rcWork


def clamp_maximize_to_work_area(window) -> None:
    """Impedir que la ventana maximizada tape la barra de tareas.

    Una ventana sin marco maximizada ocupa el monitor entero, porque Windows
    calcula ese tamaño a partir de un borde que aquí no existe.

    La corrección va por `MaximizedBounds`, la propiedad con la que WinForms
    acota el maximizado, y no interceptando WM_GETMINMAXINFO por debajo: al
    responder ese mensaje sin pasar por WinForms, el formulario se queda con
    las medidas anteriores y el control de WebView2 no se reajusta, así que la
    ventana crece pero el contenido no. Vale además para todas las vías de
    maximizar, incluidas Win+Flecha arriba y el acople al borde superior.
    """
    try:
        form = window.native
        hwnd = form.Handle.ToInt64()
    except Exception:
        return
    areas = monitor_work_area(hwnd)
    if not areas:
        return
    libre = areas[1]
    try:
        from System.Drawing import Rectangle  # noqa: PLC0415  (necesita pythonnet cargado)
        form.MaximizedBounds = Rectangle(
            libre.left, libre.top, libre.right - libre.left, libre.bottom - libre.top)
    except Exception:
        pass


class PathRejected(Exception):
    """La ruta pedida por un documento no se puede atender.

    `reason` vale "red" si apunta fuera del equipo, o "fuera" si es local pero
    queda por fuera de la carpeta del documento.
    """

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def is_network_path(path: Path) -> bool:
    """Decidir si una ruta sale del equipo.

    Una ruta UNC hace que Windows negocie autenticación con el servidor, así
    que un documento que pida `\\\\servidor\\recurso\\x.png` consigue que se
    entregue el hash de la sesión sin que el usuario toque nada. Las unidades
    de red asignadas a una letra llevan al mismo sitio por otro camino.
    """
    texto = str(path)
    if texto.startswith(("\\\\", "//")):
        return True
    unidad = os.path.splitdrive(texto)[0]
    if not unidad or not unidad.endswith(":"):
        return False
    try:
        return ctypes.windll.kernel32.GetDriveTypeW(unidad + "\\") == 4  # DRIVE_REMOTE
    except Exception:
        return False


def safe_media_path(src: str, doc_path: Path | None, *, contain: bool,
                    trusted: list[str] | None = None) -> Path:
    """Resolver una ruta pedida por el documento, o rechazarla.

    El documento controla `src` por completo, así que la comprobación se hace
    sobre la ruta **canónica**: `resolve()` deshace `..`, rutas cortas 8.3,
    enlaces simbólicos y puntos de reanálisis, de modo que lo que se valida es
    el archivo que realmente se va a abrir y no el texto que lo nombraba.
    """
    limpio = unquote(src.split("?")[0].split("#")[0]).strip()
    if not limpio:
        raise PathRejected("fuera")
    # Las rutas de dispositivo saltean la normalización del propio Windows.
    if limpio.startswith(("\\\\?\\", "\\\\.\\")):
        raise PathRejected("red")
    path = Path(limpio)
    if not path.is_absolute() and doc_path:
        path = doc_path.parent / path
    try:
        path = path.resolve()
    except OSError as e:
        raise PathRejected("fuera") from e
    if is_network_path(path):
        raise PathRejected("red")
    # Un flujo alternativo de NTFS entrega otro contenido bajo el mismo nombre.
    if ":" in path.name:
        raise PathRejected("fuera")
    if not contain or not doc_path:
        return path
    permitidas = [doc_path.parent.resolve()]
    for d in trusted or []:
        try:
            permitidas.append(Path(d).resolve())
        except OSError:
            continue
    for raiz in permitidas:
        if path == raiz or raiz in path.parents:
            return path
    raise PathRejected("fuera")


def window_under_cursor() -> int:
    """Handle de la ventana de nivel superior que está bajo el puntero."""
    x, y = cursor_position()
    child = ctypes.windll.user32.WindowFromPoint(_Point(x, y))
    if not child:
        return 0
    return ctypes.windll.user32.GetAncestor(child, 2)  # GA_ROOT


@dataclass
class Doc:
    """Un documento abierto: qué archivo es y cómo se debe guardar.

    Viaja entero cuando la pestaña se mueve a otra ventana, de modo que la
    codificación y el tipo de fin de línea originales no se pierden.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    path: Path | None = None
    encoding: str = "utf-8"
    bom: bool = False
    eol: str = "\r\n"
    mtime: float | None = None
    dirty: bool = False

    @property
    def name(self) -> str:
        return self.path.name if self.path else "Sin título"

    @property
    def ext(self) -> str:
        return self.path.suffix.lower() if self.path else ".md"

    def info(self, text: str) -> dict:
        return {"ok": True, "id": self.id, "path": str(self.path) if self.path else None,
                "name": self.name, "ext": self.ext, "text": text, "dirty": self.dirty}


class App:
    """Estado compartido por todas las ventanas del proceso."""

    def __init__(self):
        self.settings = read_settings()
        self.windows: dict[str, "WindowApi"] = {}
        self.focused: str | None = None
        self.lock = threading.Lock()

    def register(self, api: "WindowApi") -> None:
        with self.lock:
            self.windows[api._id] = api
            self.focused = api._id

    def unregister(self, window_id: str) -> None:
        with self.lock:
            self.windows.pop(window_id, None)
            if self.focused == window_id:
                self.focused = next(iter(self.windows), None)

    def focused_window(self) -> "WindowApi | None":
        with self.lock:
            return self.windows.get(self.focused) or next(iter(self.windows.values()), None)

    def window_at_cursor(self, exclude: str) -> "WindowApi | None":
        """Ventana propia bajo el puntero, sin contar la que suelta la pestaña."""
        target_hwnd = window_under_cursor()
        if not target_hwnd:
            return None
        with self.lock:
            for api in self.windows.values():
                if api._id != exclude and api.hwnd() == target_hwnd:
                    return api
        return None

    def save_settings(self, data: dict) -> None:
        self.settings.update(data)
        write_settings(self.settings)

    def remember(self, p: Path) -> None:
        recent = [str(p)] + [r for r in self.settings.get("recent", []) if r != str(p)]
        self.settings["recent"] = recent[:10]
        write_settings(self.settings)


class WindowApi:
    """Puente entre una ventana y el sistema: pestañas, archivos y ajustes.

    Cada ventana tiene su propia instancia. Los atributos llevan guion bajo
    porque pywebview publica en JavaScript todo lo que no lo lleve.
    """

    def __init__(self, app: App, initial_path: str | None = None,
                 pending: tuple[Doc, str] | None = None):
        self._app = app
        self._id = uuid.uuid4().hex[:8]
        self._window = None
        self._hwnd = 0
        self._docs: dict[str, Doc] = {}
        self._initial_path = initial_path
        self._pending = pending  # Pestaña que llega desde otra ventana.
        self._size: tuple[int, int] | None = None
        self._shown = False
        self._force_close = False
        self._maximized = False
        self._fullscreen = False
        self._rect_previo: tuple[int, int, int, int] | None = None

    def attach(self, window) -> None:
        self._window = window
        window.events.resized += self._on_resized
        window.events.closing += self._on_closing
        window.events.closed += self._on_closed

    def hwnd(self) -> int:
        """Handle nativo de la ventana, cacheado tras el primer acceso.

        El handle llega como IntPtr de .NET, que no se convierte con int().
        """
        if not self._hwnd and self._window is not None:
            try:
                self._hwnd = self._window.native.Handle.ToInt64()
            except Exception:
                self._hwnd = 0
        return self._hwnd

    # Ciclo de vida de la ventana

    def _on_resized(self, width, height) -> None:
        # Al minimizar (o durante un cierre de sesión de Windows) el evento de
        # resize llega con un tamaño casi nulo, muy por debajo de min_size. Sin
        # este filtro, esa medida se guardaba como si fuera el tamaño normal de
        # la ventana, y el siguiente arranque creaba una ventana de unos pocos
        # píxeles: invisible, aunque el proceso corriera bien.
        if width < 560 or height < 420:
            return
        self._size = (int(width), int(height))

    def _on_closing(self) -> bool:
        """Se ejecuta en el hilo de la interfaz: nada de evaluate_js aquí.

        Consultar la página desde este hilo la bloquearía, porque la respuesta
        necesita ese mismo hilo para llegar.
        """
        if self._size:
            self._app.save_settings({"width": self._size[0], "height": self._size[1]})
        if self._force_close or not any(d.dirty for d in self._docs.values()):
            return True
        # Pedir el aviso a la propia interfaz, con su estilo, sin bloquear.
        threading.Thread(target=self._ask_confirm_close, daemon=True).start()
        return False

    def _ask_confirm_close(self) -> None:
        names = [d.name for d in self._docs.values() if d.dirty]
        try:
            self._window.evaluate_js(
                f"window.__confirmClose && window.__confirmClose({json.dumps(names)})")
        except Exception:
            self.force_close()

    def _on_closed(self) -> None:
        self._app.unregister(self._id)

    def force_close(self) -> None:
        """Cerrar sin volver a preguntar. Lo llama la interfaz tras confirmar."""
        self._force_close = True
        if self._window:
            self._window.destroy()

    def ready(self) -> None:
        """Mostrar la ventana cuando la interfaz terminó de cargar.

        Evita el destello de fondo mientras WebView2 se inicializa.
        """
        if self._window and not self._shown:
            self._shown = True
            restore_resize_border(self.hwnd())
            clamp_maximize_to_work_area(self._window)
            self._window.show()
        flush_pending_paths()

    def focus_window(self) -> None:
        with self._app.lock:
            self._app.focused = self._id

    def startup(self) -> dict:
        """Entregar los ajustes y la pestaña inicial a la interfaz."""
        if self._pending:
            doc, text = self._pending
            self._pending = None
            self._docs[doc.id] = doc
            info = doc.info(text)
        elif self._initial_path:
            info = self.open_into(uuid.uuid4().hex[:8], str(self._initial_path))
            self._initial_path = None
        else:
            info = self.new_tab()
        return {"doc": info, "settings": self._app.settings, "version": VERSION,
                "installed": winshell.is_installed(), "frozen": winshell.is_frozen()}

    # Pestañas

    def new_tab(self) -> dict:
        doc = Doc()
        self._docs[doc.id] = doc
        return doc.info("")

    def close_tab(self, doc_id: str) -> None:
        self._docs.pop(doc_id, None)

    def set_dirty(self, doc_id: str, flag: bool) -> None:
        doc = self._docs.get(doc_id)
        if doc:
            doc.dirty = bool(flag)

    def new_window(self, path: str | None = None) -> dict:
        create_window(self._app, path=path)
        return {"ok": True}

    # Barra de título propia

    def minimize_window(self) -> None:
        self._window.minimize()

    def close_window(self) -> None:
        """Cerrar la ventana desde el botón de la barra propia.

        Pasa por destroy() y no por force_close() para que el aviso de
        cambios sin guardar siga saliendo: destroy() dispara el evento
        closing, que es donde se decide si el cierre sigue adelante.
        """
        if self._window:
            self._window.destroy()

    def toggle_maximize(self) -> bool:
        """Alternar maximizado. Devuelve el estado nuevo para el icono."""
        if self._fullscreen:
            self.toggle_fullscreen()
            return False
        self._maximized = not self._maximized
        if self._maximized:
            # Recalcular por si la ventana cambió de monitor: MaximizedBounds
            # guarda un rectángulo concreto, no "el monitor de turno".
            clamp_maximize_to_work_area(self._window)
            self._window.maximize()
        else:
            self._window.restore()
        return self._maximized

    def toggle_fullscreen(self) -> bool:
        """Alternar pantalla completa sin bordes, tapando la barra de tareas.

        No usa el maximizado de Windows, que ahora respeta el área libre del
        monitor: coloca la ventana sobre el rectángulo completo de la pantalla
        y guarda la posición anterior para volver a ella.
        """
        hwnd = self.hwnd()
        if not hwnd:
            return self._fullscreen
        user32 = ctypes.windll.user32
        if self._fullscreen:
            self._fullscreen = False
            rect = self._rect_previo
            if rect:
                user32.SetWindowPos(hwnd, 0, rect[0], rect[1],
                                    rect[2] - rect[0], rect[3] - rect[1], 0x0004)
            if self._maximized:
                self._window.maximize()
            return False
        if self._maximized:
            self._maximized = False
            self._window.restore()
        previo = (ctypes.c_long * 4)()
        user32.GetWindowRect(hwnd, ctypes.byref(previo))
        self._rect_previo = (previo[0], previo[1], previo[2], previo[3])
        areas = monitor_work_area(hwnd)
        if not areas:
            return False
        pantalla = areas[0]
        self._fullscreen = True
        user32.SetWindowPos(hwnd, 0, pantalla.left, pantalla.top,
                            pantalla.right - pantalla.left,
                            pantalla.bottom - pantalla.top, 0x0004)  # SWP_NOZORDER
        return True

    def move_window(self, dx: int, dy: int) -> None:
        """Desplazar la ventana mientras se arrastra por la barra de pestañas."""
        hwnd = self.hwnd()
        if not hwnd:
            return
        if self._fullscreen:  # Arrastrar sale de pantalla completa.
            self.toggle_fullscreen()
        elif self._maximized:  # Arrastrar una ventana maximizada la restaura.
            self._maximized = False
            self._window.restore()
        rect = (ctypes.c_long * 4)()
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
        ctypes.windll.user32.SetWindowPos(
            hwnd, 0, rect[0] + int(dx), rect[1] + int(dy), 0, 0,
            0x0001 | 0x0004)  # SWP_NOSIZE | SWP_NOZORDER

    def move_tab_to_new_window(self, doc_id: str, text: str) -> dict:
        """Mandar una pestaña a una ventana nueva desde el menú contextual."""
        doc = self._docs.pop(doc_id, None)
        if not doc:
            return {"ok": False}
        create_window(self._app, pending=(doc, text))
        return {"ok": True}

    def drop_tab(self, doc_id: str, text: str, allow_new_window: bool = True) -> dict:
        """Soltar una pestaña fuera de su barra.

        Si el puntero está sobre otra ventana de la aplicación, la pestaña se
        muda allí; si no, se abre una ventana nueva donde se soltó. El Doc
        viaja entero, así que no hace falta guardar antes de mover.
        """
        doc = self._docs.get(doc_id)
        if not doc:
            return {"ok": False, "error": "La pestaña ya no existe."}
        target = self._app.window_at_cursor(exclude=self._id)
        if target is None and not allow_new_window:
            return {"ok": False, "kept": True}
        del self._docs[doc_id]
        if target is not None:
            target.accept_tab(doc, text)
            return {"ok": True, "moved": True}
        x, y = cursor_position()
        create_window(self._app, pending=(doc, text), x=x - 120, y=max(0, y - 20))
        return {"ok": True, "moved": False}

    def accept_tab(self, doc: Doc, text: str) -> None:
        """Recibir una pestaña que viene de otra ventana."""
        self._docs[doc.id] = doc
        payload = json.dumps(doc.info(text))
        try:
            self._window.evaluate_js(f"window.__acceptTab && window.__acceptTab({payload})")
            self._window.restore()
        except Exception:
            pass

    def open_external_tab(self, path: str) -> None:
        """Abrir un archivo llegado de otra instancia como pestaña nueva."""
        try:
            self._window.restore()
        except Exception:
            pass
        try:
            self._window.evaluate_js(
                f"window.__openExternalTab && window.__openExternalTab({json.dumps(path)})")
        except Exception:
            pass

    # Lectura y escritura

    def _decode(self, doc: Doc, raw: bytes) -> str:
        """Detectar la codificación y recordarla para guardar igual que estaba.

        UTF-16 se considera solo con BOM: sin él, Python decodifica como UTF-16
        casi cualquier cosa y guardar convertiría un archivo ANSI en basura.
        """
        doc.bom = raw.startswith(b"\xef\xbb\xbf")
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            doc.encoding = "utf-16"
            return raw.decode("utf-16")
        try:
            text = raw.decode("utf-8-sig")
            doc.encoding = "utf-8"
            return text
        except UnicodeDecodeError:
            pass
        for enc in ("cp1252", "latin-1"):
            try:
                text = raw.decode(enc)
                doc.encoding = enc
                return text
            except UnicodeDecodeError:
                continue
        doc.encoding = "utf-8"
        return raw.decode("utf-8", "replace")

    def open_into(self, doc_id: str, path: str, from_document: bool = False) -> dict:
        """Cargar `path` en la pestaña `doc_id`, reutilizándola si ya existe.

        Las rutas relativas se resuelven contra el archivo actual de esa
        pestaña, para que los enlaces entre documentos funcionen.
        """
        doc = self._docs.get(doc_id) or Doc(id=doc_id)
        # Solo se filtran las rutas que propone el propio documento: un enlace
        # a \\servidor\recurso entrega credenciales de red al hacer clic. Un
        # archivo que el usuario eligió a mano se abre esté donde esté, aunque
        # sea una unidad de red suya.
        if from_document:
            try:
                p = safe_media_path(path, doc.path, contain=False)
            except PathRejected:
                return {"ok": False,
                        "error": "El enlace apunta fuera del equipo y no se abrió."}
        else:
            p = Path(unquote(path))
            if not p.is_absolute() and doc.path:
                p = doc.path.parent / p
            p = p.resolve()
        try:
            raw = p.read_bytes()
        except OSError as e:
            return {"ok": False, "error": f"No se pudo abrir el archivo: {e}"}
        text = self._decode(doc, raw)
        doc.eol = "\r\n" if "\r\n" in text else "\n"
        doc.path = p
        doc.mtime = p.stat().st_mtime
        doc.dirty = False
        self._docs[doc.id] = doc
        self._app.remember(p)
        return doc.info(text.replace("\r\n", "\n").replace("\r", "\n"))

    def save(self, doc_id: str, text: str) -> dict:
        doc = self._docs.get(doc_id)
        if not doc:
            return {"ok": False, "error": "La pestaña ya no existe."}
        if not doc.path:
            return self.save_as(doc_id, text, ".md")
        try:
            self._write(doc, doc.path, text)
        except OSError as e:
            return {"ok": False, "error": f"No se pudo guardar: {e}"}
        doc.mtime = doc.path.stat().st_mtime
        doc.dirty = False
        return {"ok": True, "id": doc.id, "path": str(doc.path), "name": doc.name}

    def save_as(self, doc_id: str, text: str, ext: str = ".md") -> dict:
        doc = self._docs.get(doc_id) or Doc(id=doc_id)
        start = str(doc.path.parent) if doc.path else str(Path.home())
        name = (doc.path.stem if doc.path else "documento") + ext
        types = ("Markdown (*.md;*.markdown)", "Texto (*.txt)", "Todos los archivos (*.*)")
        res = self._window.create_file_dialog(
            webview.SAVE_DIALOG, directory=start, save_filename=name, file_types=types)
        if not res:
            return {"ok": False, "cancelled": True}
        target = Path(res if isinstance(res, str) else res[0])
        if not target.suffix:
            target = target.with_suffix(ext)
        try:
            self._write(doc, target, text)
        except OSError as e:
            return {"ok": False, "error": f"No se pudo guardar: {e}"}
        doc.path = target
        doc.mtime = target.stat().st_mtime
        doc.dirty = False
        self._docs[doc.id] = doc
        self._app.remember(target)
        return {"ok": True, "id": doc.id, "path": str(target), "name": target.name,
                "ext": target.suffix.lower()}

    def _write(self, doc: Doc, target: Path, text: str) -> None:
        """Escribir de forma atómica: archivo temporal en la misma carpeta y reemplazo."""
        data = text.replace("\n", doc.eol).encode(doc.encoding, "replace")
        if doc.bom and doc.encoding == "utf-8":
            data = b"\xef\xbb\xbf" + data
        fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def pick_folder(self) -> str:
        """Elegir una carpeta de confianza desde la configuración avanzada."""
        res = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        if not res:
            return ""
        return str(res if isinstance(res, str) else res[0])

    def open_dialog(self) -> list:
        """Mostrar el selector de archivos y devolver las rutas elegidas, sin cargarlas."""
        start = str(Path.home())
        for doc in self._docs.values():
            if doc.path:
                start = str(doc.path.parent)
                break
        res = self._window.create_file_dialog(
            webview.OPEN_DIALOG, directory=start, allow_multiple=True,
            file_types=("Markdown y texto (*.md;*.markdown;*.mdown;*.txt)",
                        "Todos los archivos (*.*)"))
        return list(res) if res else []

    def changed_on_disk(self, doc_id: str) -> bool:
        """Informar si otro programa modificó el archivo desde la última lectura."""
        doc = self._docs.get(doc_id)
        if not doc or not doc.path or doc.mtime is None:
            return False
        try:
            return doc.path.stat().st_mtime > doc.mtime + 0.5
        except OSError:
            return False

    def image_data(self, doc_id: str, src: str, override: bool = False) -> dict:
        """Devolver una imagen local del documento como data URI.

        La interfaz corre sobre http://127.0.0.1, origen desde el cual Chromium
        rechaza los subrecursos file://. Solo se atienden extensiones de imagen.

        `override` levanta la contención para una imagen concreta que el
        usuario pidió cargar; nunca levanta el bloqueo de rutas de red.
        """
        doc = self._docs.get(doc_id)
        if not doc or not doc.path:
            return {"ok": False, "reason": "fuera"}
        s = self._app.settings
        contain = bool(s.get("contain_images", True)) and not override
        try:
            path = safe_media_path(src, doc.path, contain=contain,
                                   trusted=s.get("trusted_dirs") or [])
        except PathRejected as e:
            return {"ok": False, "reason": e.reason}
        try:
            if path.suffix.lower() not in IMAGE_TYPES:
                return {"ok": False, "reason": "tipo"}
            if path.stat().st_size > MAX_IMAGE_BYTES:
                return {"ok": False, "reason": "tamaño"}
            raw = path.read_bytes()
        except (OSError, ValueError):
            return {"ok": False, "reason": "falta"}
        mime = IMAGE_TYPES[path.suffix.lower()]
        return {"ok": True,
                "uri": f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"}

    def export_html(self, doc_id: str, body: str, title: str) -> dict:
        doc = self._docs.get(doc_id)
        css = resource("web", "styles.css").read_text("utf-8")
        katex = resource("web", "vendor", "katex.min.css").read_text("utf-8")
        safe_title = title.replace("<", "").replace(">", "")
        html = ('<!doctype html><html lang="es"><head><meta charset="utf-8">'
                f"<title>{safe_title}</title><style>{css}\n{katex}</style></head>"
                f'<body class="exported"><article class="doc">{body}</article></body></html>')
        name = (doc.path.stem if doc and doc.path else "documento") + ".html"
        start = str(doc.path.parent) if doc and doc.path else str(Path.home())
        res = self._window.create_file_dialog(
            webview.SAVE_DIALOG, directory=start, save_filename=name,
            file_types=("Página HTML (*.html)",))
        if not res:
            return {"ok": False, "cancelled": True}
        target = Path(res if isinstance(res, str) else res[0])
        try:
            target.write_text(html, "utf-8")
        except OSError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "path": str(target)}

    def reveal(self, doc_id: str) -> None:
        doc = self._docs.get(doc_id)
        if doc and doc.path:
            os.startfile(doc.path.parent)

    # Ajustes y utilidades

    def save_settings(self, data: dict) -> None:
        self._app.save_settings(data)

    def recent(self) -> list:
        return [{"path": r, "name": Path(r).name}
                for r in self._app.settings.get("recent", []) if Path(r).exists()]

    def open_external(self, url: str) -> None:
        if url.startswith(("http://", "https://", "mailto:")):
            webbrowser.open(url)

    # Integración con Windows

    def install(self) -> dict:
        return winshell.install()

    def shell_status(self) -> dict:
        return {"installed": winshell.is_installed(), "registered": winshell.is_registered(),
                "frozen": winshell.is_frozen(), "exe": str(winshell.current_exe())}

    def open_default_apps(self) -> None:
        os.startfile("ms-settings:defaultapps")


def create_window(app: App, *, path: str | None = None,
                  pending: tuple[Doc, str] | None = None,
                  x: int | None = None, y: int | None = None) -> WindowApi:
    """Crear una ventana. Funciona antes y después de webview.start()."""
    api = WindowApi(app, initial_path=path, pending=pending)
    s = app.settings
    extra = {"x": int(x), "y": int(y)} if x is not None and y is not None else {}
    window = webview.create_window(
        APP_NAME, url=str(resource("web", "index.html")), js_api=api,
        width=int(s.get("width", 1100)), height=int(s.get("height", 780)),
        min_size=(560, 420), background_color=DARK_BG, text_select=True,
        hidden=True, frameless=True, easy_drag=False, **extra)
    api.attach(window)
    app.register(api)
    # Si la interfaz no llegara a arrancar, la ventana se muestra igual.
    threading.Timer(6.0, api.ready).start()
    return api


# Instancia única: al abrir un archivo desde el Explorador con una ventana ya
# abierta, se agrega como pestaña nueva en lugar de abrir otra ventana.

def _acquire_singleton() -> bool:
    """Intentar convertirse en la instancia principal. Conserva el socket vivo."""
    global _singleton_socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", SINGLETON_PORT))
    except OSError:
        s.close()
        return False
    # Cola amplia: seleccionar varios archivos en el Explorador lanza un
    # proceso por archivo y todos se conectan a la vez.
    s.listen(64)
    _singleton_socket = s
    return True


def _forward_to_primary(path: str) -> bool:
    """Enviar una ruta a la instancia principal por el socket de instancia única.

    Reintenta unos segundos: con muchos archivos a la vez, la principal puede
    estar todavía enlazando el puerto cuando llegan las demás instancias.
    """
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", SINGLETON_PORT), timeout=1) as c:
                c.sendall((path or "").encode("utf-8") + b"\n")
            return True
        except OSError:
            time.sleep(0.15)
    return False


def deliver_path(path: str) -> None:
    """Abrir una ruta recibida de otra instancia, o encolarla si aún no se puede."""
    window = _app.focused_window() if _app else None
    if window is None or not window._shown:
        with _pending_lock:
            _pending_paths.append(path)
        return
    window.open_external_tab(path)


def flush_pending_paths() -> None:
    """Abrir las rutas que llegaron mientras la interfaz arrancaba."""
    with _pending_lock:
        paths = list(_pending_paths)
        _pending_paths.clear()
    window = _app.focused_window() if _app else None
    if window is None:
        return
    for path in paths:
        window.open_external_tab(path)


def _run_singleton_server() -> None:
    """Escuchar rutas reenviadas por otras instancias y abrirlas como pestañas."""
    server = _singleton_socket
    if not server:
        return
    while True:
        try:
            conn, _addr = server.accept()
        except OSError:
            return
        try:
            conn.settimeout(2)
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
        except OSError:
            data = b""
        finally:
            conn.close()
        path = data.decode("utf-8", "replace").strip()
        if path:
            deliver_path(path)


def main() -> int:
    global _app

    args = [a for a in sys.argv[1:] if a]
    if "--uninstall" in args:
        winshell.uninstall(confirm=True)
        return 0
    if "--register" in args:
        winshell.register(winshell.current_exe())
        return 0

    new_window = "--new-window" in args

    # El Explorador entrega la ruta entre comillas; desde la consola puede
    # llegar partida en varios argumentos.
    paths = [a for a in args if not a.startswith("-")]
    target = next((p for p in paths if Path(p).exists()), None)
    if target is None and paths:
        joined = " ".join(paths)
        target = joined if Path(joined).exists() else None

    if not new_window:
        if _acquire_singleton():
            threading.Thread(target=_run_singleton_server, daemon=True).start()
        elif _forward_to_primary(target or ""):
            return 0
        # Si no se pudo reenviar, esta instancia abre su propia ventana.

    clear_web_cache()
    _app = App()
    create_window(_app, path=target)

    # Perfil de WebView2 persistente. En modo privado pywebview crea uno nuevo
    # en cada arranque y lo borra al salir: eso agrega segundos de espera al
    # abrir y al cerrar la aplicación.
    webview.start(gui="edgechromium", debug="--debug" in args,
                  private_mode=False, storage_path=str(WEBVIEW_PROFILE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
