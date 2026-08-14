"""Prueba de la E/S de archivos: no puede corromper lo que ya está en disco.

    python tests/test_files.py
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import main  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="visormd-io-"))
main.CONFIG = TMP / "settings.json"
TEXT = "# Título\n\nAcentos: ñáéíóú €.\n\n- uno\n- dos\n"


def new_api() -> "main.WindowApi":
    return main.WindowApi(main.App())


def roundtrip(name: str, raw: bytes) -> tuple[bytes, str]:
    p = TMP / name
    p.write_bytes(raw)
    api = new_api()
    doc = api.open_into("t1", str(p))
    api.save("t1", doc["text"])
    return p.read_bytes(), doc["text"]


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(("  OK   " if ok else "  FALLA") + f"  {name}" + (f"  -> {detail}" if detail else ""))
    return ok


def run() -> int:
    results = []

    raw = TEXT.replace("\n", "\r\n").encode("utf-8")
    out, text = roundtrip("crlf.md", raw)
    results.append(check("preserva CRLF y acentos", out == raw, repr(out[:20])))
    results.append(check("el editor recibe solo LF", "\r" not in text))

    raw = b"\xef\xbb\xbf" + TEXT.encode("utf-8")
    out, _ = roundtrip("bom.md", raw)
    results.append(check("preserva el BOM de UTF-8", out == raw, repr(out[:6])))

    raw = TEXT.encode("cp1252")
    out, text = roundtrip("ansi.md", raw.replace(b"\xe2\x82\xac", b"E"))
    results.append(check("lee y reescribe ANSI (cp1252)", "ñáéíóú" in text, repr(out[:12])))

    p = TMP / "atomico.md"
    p.write_text(TEXT, "utf-8")
    api = new_api()
    api.open_into("t2", str(p))
    api.save("t2", "contenido nuevo\n")
    sobras = [f.name for f in TMP.iterdir() if f.suffix == ".tmp"]
    results.append(check("no deja archivos .tmp sueltos", not sobras, str(sobras)))
    results.append(check("guarda el contenido nuevo", p.read_text("utf-8") == "contenido nuevo\n"))

    api = new_api()
    api.open_into("t3", str(p))
    results.append(check("detecta cambios externos", not api.changed_on_disk("t3")))
    p.write_text("otro programa escribió acá\n", "utf-8")
    import os
    import time
    os.utime(p, (time.time() + 5, time.time() + 5))
    results.append(check("detecta cambios externos (tras modificar)", api.changed_on_disk("t3")))

    # Dos pestañas independientes: guardar una no debe tocar la otra.
    api = new_api()
    pa, pb = TMP / "a.md", TMP / "b.md"
    pa.write_text("A original\n", "utf-8")
    pb.write_text("B original\n", "utf-8")
    api.open_into("ta", str(pa))
    api.open_into("tb", str(pb))
    api.save("ta", "A editado\n")
    results.append(check("pestañas independientes: A cambia",
                          pa.read_text("utf-8") == "A editado\n"))
    results.append(check("pestañas independientes: B no cambia",
                          pb.read_text("utf-8") == "B original\n"))
    api.close_tab("ta")
    results.append(check("cerrar una pestaña no afecta a la otra",
                          api.changed_on_disk("tb") is False))

    # Mover una pestaña a otra ventana por el camino real: drop_tab decide el
    # destino y el documento entero viaja con su codificación y fin de línea.
    app = main.App()
    origen, destino = main.WindowApi(app), main.WindowApi(app)
    recibidos = []
    destino.accept_tab = lambda doc, text: recibidos.append((doc, text))
    app.window_at_cursor = lambda exclude: destino

    pc = TMP / "viaje.md"
    pc.write_bytes("Texto con ñ\r\n".encode("cp1252"))
    doc = origen.open_into("tv", str(pc))
    res = origen.drop_tab("tv", doc["text"] + "editado\n")
    results.append(check("drop_tab entrega la pestaña a la otra ventana",
                          res.get("moved") is True and len(recibidos) == 1))
    results.append(check("la pestaña sale de la ventana de origen",
                          "tv" not in origen._docs))

    movido, texto = recibidos[0]
    destino._docs[movido.id] = movido
    destino.save(movido.id, texto)
    crudo = pc.read_bytes()
    results.append(check("la pestaña movida conserva la codificación",
                          b"\xf1" in crudo, repr(crudo[:14])))
    results.append(check("la pestaña movida conserva el fin de línea CRLF",
                          b"\r\n" in crudo))
    results.append(check("la pestaña movida conserva el texto editado",
                          crudo.endswith(b"editado\r\n"), repr(crudo[-12:])))

    # Con una sola pestaña abierta y sin otra ventana debajo del puntero, no
    # se abre una ventana nueva: soltarla no debe dejar la ventana sin nada.
    app2 = main.App()
    sola = main.WindowApi(app2)
    app2.window_at_cursor = lambda exclude: None
    sola.open_into("unica", str(pc))
    res2 = sola.drop_tab("unica", "texto", allow_new_window=False)
    results.append(check("soltar la única pestaña no la saca de la ventana",
                          res2.get("kept") is True and "unica" in sola._docs))

    ok = all(results)
    print("\n" + ("TODO OK" if ok else "HAY FALLAS"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
