"""Suite de seguridad: abre documentos hostiles y comprueba propiedades.

    python tests/seguridad.py

Los archivos de tests/security/ son datos, no instrucciones. Esta suite mira
en qué quedaron convertidos dentro del DOM; nunca ejecuta lo que contienen.
Cada comprobación afirma una propiedad concreta —no hay atributos on*, no
salió una petición a la red, la ruta quedó fuera— y no simplemente que la
aplicación no se cayó.
"""

import json
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import webview  # noqa: E402

import main  # noqa: E402

CORPUS = ROOT / "tests" / "security"
failures = []


def check(name, ok, detail=""):
    print(("  OK   " if ok else "  FALLA") + f"  {name}" + (f"  -> {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def wait_until(window, expression, timeout=25):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if window.evaluate_js(expression):
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.25)
    return False


def cargar(window, nombre, timeout=30):
    """Abrir un documento del corpus en la pestaña activa y esperar el render."""
    ruta = CORPUS / nombre
    window.evaluate_js(f"window.__openExternalTab({json.dumps(str(ruta))})")
    ok = wait_until(window, "(document.querySelector('.tab.active .tab-name')||{})"
                            f".textContent === {json.dumps(nombre)}", timeout)
    # Los diagramas son asíncronos: sin esperarlos se mide el DOM a medio armar.
    wait_until(window, "document.querySelectorAll('.mermaid-block').length === 0"
                       " || document.querySelectorAll('.mermaid-block svg,"
                       " .mermaid-error').length > 0", timeout)
    time.sleep(0.6)
    return ok


# Marcadores que los payloads del corpus intentan dejar en window. Que ninguno
# exista es la prueba de que nada se ejecutó.
BANDERAS = """(() => Object.keys(window)
  .filter((k) => /^__(XSS|P|M|K|FM)\\d*$/.test(k)))()"""


def check_xss(w):
    cargar(w, "xss.md")
    r = w.evaluate_js("""({
      script: document.querySelectorAll('#preview script').length,
      eventos: [...document.querySelectorAll('#preview *')]
        .flatMap((el) => [...el.attributes].map((a) => a.name))
        .filter((n) => n.toLowerCase().startsWith('on')),
      marcos: document.querySelectorAll('#preview iframe, #preview frame').length,
      objetos: document.querySelectorAll('#preview object, #preview embed').length,
      formularios: document.querySelectorAll('#preview form').length,
      estilos: document.querySelectorAll('#preview style').length,
      base: document.querySelectorAll('#preview base').length,
      foreign: document.querySelectorAll('#preview foreignObject').length,
      jsHref: [...document.querySelectorAll('#preview [href], #preview [src]')]
        .map((el) => (el.getAttribute('href') || el.getAttribute('src') || ''))
        .filter((v) => /^\\s*(javascript|vbscript|data:text\\/html)/i.test(v)),
    })""")
    check("no queda ningún <script> en el documento", r["script"] == 0, r["script"])
    check("no queda ningún atributo on*", not r["eventos"], r["eventos"][:5])
    check("no quedan marcos incrustados", r["marcos"] == 0, r["marcos"])
    check("no quedan object ni embed", r["objetos"] == 0, r["objetos"])
    check("no quedan formularios", r["formularios"] == 0, r["formularios"])
    check("no quedan estilos globales", r["estilos"] == 0, r["estilos"])
    check("no queda una etiqueta base", r["base"] == 0, r["base"])
    check("no queda foreignObject", r["foreign"] == 0, r["foreign"])
    check("ninguna URL de ejecución sobrevive", not r["jsHref"], r["jsHref"][:3])
    check("ningún payload llegó a ejecutarse", not w.evaluate_js(BANDERAS),
          w.evaluate_js(BANDERAS))


PERMITIDOS = ("http:", "https:", "mailto:")


def check_protocolos(w):
    cargar(w, "protocols.md")
    r = w.evaluate_js("""({
      todos: [...document.querySelectorAll('#preview a')]
        .map((a) => a.getAttribute('href') || ''),
      permitidos: [...document.querySelectorAll('#preview a[href]')]
        .map((a) => a.getAttribute('href'))
        .filter((h) => /^(https?:|mailto:)/i.test(h)).length,
    })""")
    malos = [h for h in r["todos"] if ":" in h.split("/")[0]
             and not h.lower().startswith(PERMITIDOS)]
    check("ningún esquema fuera de la allowlist sobrevive", not malos, malos[:4])
    check("http, https y mailto siguen funcionando", r["permitidos"] >= 3, r["permitidos"])
    check("las rutas UNC no quedan como enlace",
          not [h for h in r["todos"] if h.startswith("\\\\")],
          [h for h in r["todos"] if h.startswith("\\\\")])


def check_imagenes(w):
    """Ninguna petición sale a la red al abrir el documento.

    Se mide con un PerformanceObserver instalado antes de renderizar: registra
    cualquier recurso que el navegador haya intentado traer, incluidos los que
    fallaron, así que detecta el intento aunque el servidor no exista.
    """
    w.evaluate_js("""
      window.__net = [];
      new PerformanceObserver((l) => {
        for (const e of l.getEntries()) window.__net.push(e.name);
      }).observe({ entryTypes: ['resource'] });
    """)
    cargar(w, "images.md")
    remotas = w.evaluate_js(
        "(window.__net || []).filter((u) => !/^https?:\\/\\/(127\\.0\\.0\\.1|localhost)/.test(u))")
    check("abrir el documento no genera ninguna petición remota", not remotas, remotas[:4])
    r = w.evaluate_js("""({
      bloqueadas: document.querySelectorAll('#preview img[data-blocked]').length,
      conSrcRemoto: [...document.querySelectorAll('#preview img[src]')]
        .filter((i) => /^(https?:|\\/\\/)/i.test(i.getAttribute('src'))).length,
      enlaces: document.querySelectorAll('#preview link').length,
      medios: document.querySelectorAll('#preview video, #preview audio').length,
    })""")
    check("las imágenes remotas quedan marcadas como bloqueadas",
          r["bloqueadas"] >= 2, r["bloqueadas"])
    check("ninguna imagen conserva una URL remota", r["conSrcRemoto"] == 0, r["conSrcRemoto"])
    check("no quedan hojas de estilo ni precargas", r["enlaces"] == 0, r["enlaces"])
    check("no quedan video ni audio", r["medios"] == 0, r["medios"])


def check_mermaid(w):
    cargar(w, "mermaid.md")
    r = w.evaluate_js("""({
      svg: document.querySelectorAll('.mermaid-block svg').length,
      script: document.querySelectorAll('.mermaid-block script').length,
      foreign: document.querySelectorAll('.mermaid-block foreignObject').length,
      eventos: [...document.querySelectorAll('.mermaid-block *')]
        .flatMap((el) => [...el.attributes].map((a) => a.name))
        .filter((n) => n.toLowerCase().startsWith('on')),
      urls: [...document.querySelectorAll('.mermaid-block [href], .mermaid-block [src]')]
        .map((el) => el.getAttribute('href') || el.getAttribute('src') || '')
        .filter((v) => /^(javascript|data:text\\/html|https?:)/i.test(v)),
      estilo: document.querySelectorAll('.mermaid-block style').length,
      rotulos: [...document.querySelectorAll('.mermaid-block svg')]
        .filter((s) => (s.textContent || '').replace(/\s/g, '').length > 3).length,
    })""")
    check("los diagramas válidos siguen dibujándose", r["svg"] >= 2, r["svg"])
    # Un diagrama sin rótulos son cajas vacías: pasó de verdad al descartar
    # foreignObject, y el SVG seguía estando ahí para disimularlo.
    check("los diagramas conservan el texto de sus nodos",
          r["rotulos"] >= 2, f'{r["rotulos"]} de {r["svg"]} con texto')
    check("el SVG del diagrama no trae script", r["script"] == 0, r["script"])
    check("el SVG del diagrama no trae foreignObject", r["foreign"] == 0, r["foreign"])
    check("el SVG del diagrama no trae atributos on*", not r["eventos"], r["eventos"][:4])
    check("el diagrama no conserva URLs activas ni remotas", not r["urls"], r["urls"][:3])
    # El <style> es propio de mermaid y va acotado con el id del diagrama: sin
    # él los diagramas pierden todo el color.
    check("el estilo propio del diagrama se conserva", r["estilo"] >= 1, r["estilo"])
    check("ningún diagrama ejecutó nada", not w.evaluate_js(BANDERAS))


def check_katex(w):
    cargar(w, "katex.md")
    r = w.evaluate_js("""({
      formulas: document.querySelectorAll('#preview .katex').length,
      enlaces: document.querySelectorAll('#preview .katex a').length,
      imagenes: document.querySelectorAll('#preview .katex img').length,
      idRobado: !!document.querySelector('#preview .katex #dialog'),
      ancho: document.getElementById('preview').scrollWidth,
    })""")
    check("las fórmulas válidas siguen renderizando", r["formulas"] >= 2, r["formulas"])
    check("una fórmula no puede crear enlaces", r["enlaces"] == 0, r["enlaces"])
    check("una fórmula no puede cargar imágenes", r["imagenes"] == 0, r["imagenes"])
    check("una fórmula no puede robar un id de la interfaz", not r["idRobado"])
    check("una fórmula gigante no desborda la página sin límite",
          r["ancho"] < 100000, r["ancho"])
    check("ninguna fórmula ejecutó nada", not w.evaluate_js(BANDERAS))


def check_clobbering(w):
    cargar(w, "dom-clobbering.md")
    r = w.evaluate_js("""(() => {
      const dentro = (id) => {
        const el = document.getElementById(id);
        return !!(el && el.closest('#preview'));
      };
      return {
        robados: ['dialog', 'menu', 'ctxmenu', 'toast', 'editor', 'preview',
                  'dlg-ok', 'dlg-body', 'tablist', 'findbar', 'switch']
          .filter(dentro),
        apiViva: !!(window.pywebview && window.pywebview.api),
        renderVivo: typeof window.Render === 'object' && typeof Render.render === 'function',
        editorVivo: typeof window.Editor === 'object',
      };
    })()""")
    # getElementById devuelve el primero en orden de árbol y #preview está
    # antes que #menu y #dialog: sin la instantánea del arranque, estos ids
    # se los quedaría el documento.
    check("el documento se queda con ids que chocan con la interfaz",
          len(r["robados"]) > 0, r["robados"])
    check("aun así la aplicación conserva sus propios elementos",
          w.evaluate_js("""(() => {
            const ui = ['dialog', 'menu', 'ctxmenu', 'toast', 'dlg-ok'];
            return ui.every((id) => !window.__uiRef(id).closest('#preview'));
          })()"""))
    check("el puente con Python sigue en pie", r["apiViva"])
    check("los módulos de la aplicación no fueron sustituidos",
          r["renderVivo"] and r["editorVivo"])


def check_oculto(w):
    cargar(w, "hidden-content.md")
    r = w.evaluate_js("""({
      copiaOculta: [...document.querySelectorAll('.codeblock code')]
        .filter((c) => c.textContent.trim() !== (c.innerText || '').trim()).length,
      estilosEnCodigo: document.querySelectorAll('.codeblock [style], .codeblock [hidden]').length,
      desbordeH: document.documentElement.scrollWidth <= window.innerWidth + 1,
      contencion: getComputedStyle(document.getElementById('preview')).contain,
      barraTapada: (() => {
        const barra = document.getElementById('tabbar').getBoundingClientRect();
        const x = barra.left + barra.width / 2;
        const y = barra.top + barra.height / 2;
        const el = document.elementFromPoint(x, y);
        return !!(el && el.closest('#preview'));
      })(),
    })""")
    check("lo que se copia coincide con lo que se ve",
          r["copiaOculta"] == 0, r["copiaOculta"])
    check("los bloques de código pierden style y hidden",
          r["estilosEnCodigo"] == 0, r["estilosEnCodigo"])
    check("el documento no desborda la página a lo ancho", r["desbordeH"])
    check("la vista del documento está contenida", "paint" in (r["contencion"] or ""),
          r["contencion"])
    check("el documento no puede cubrir la barra de herramientas", not r["barraTapada"])


def check_frontmatter(w):
    cargar(w, "frontmatter.md")
    r = w.evaluate_js("""({
      texto: document.getElementById('preview').textContent,
      contaminado: ({}).contaminado === true || Object.prototype.contaminado === true,
    })""")
    check("el frontmatter no se muestra", "!!python/object/apply" not in r["texto"])
    check("el prototipo no quedó contaminado", not r["contaminado"])
    check("el cuerpo del documento sí se muestra",
          "no interpreta el frontmatter" in r["texto"])
    check("el frontmatter no ejecutó nada", not w.evaluate_js(BANDERAS))


def check_defectuoso(w):
    """Markdown mal formado de una conversión automática: debe renderizar entero."""
    w.evaluate_js("window.__errores = []; "
                  "window.addEventListener('error', (e) => window.__errores.push(String(e.message)));")
    cargar(w, "conversion-defectuosa.md")
    r = w.evaluate_js("""({
      errores: window.__errores || [],
      encabezados: document.querySelectorAll('#preview h2').length,
      tablas: document.querySelectorAll('#preview table').length,
      deformada: document.getElementById('preview').textContent.includes('| Negrita |'),
      diagramas: document.querySelectorAll('.mermaid-block svg, .mermaid-error').length,
      final: document.getElementById('preview').textContent.includes('Pagina 14 de 14'),
    })""")
    check("un Markdown defectuoso no lanza excepciones", not r["errores"], r["errores"][:2])
    check("se renderizan sus encabezados", r["encabezados"] >= 8, r["encabezados"])
    check("las tablas bien formadas se renderizan", r["tablas"] >= 1, r["tablas"])
    # Una cabecera con más columnas que su fila separadora no es una tabla para
    # markdown-it, y hace bien: queda como texto en vez de inventar celdas.
    check("una tabla deformada degrada a texto sin romper nada", r["deformada"])
    check("los diagramas rotos se resuelven de algún modo", r["diagramas"] >= 2, r["diagramas"])
    check("el documento llega hasta el final", r["final"])


def check_traversal(w):
    """La contención de rutas se prueba contra Python, que es quien la aplica."""
    carpeta = Path(tempfile.mkdtemp(prefix="visormd-sec-"))
    (carpeta / "medios").mkdir()
    doc = carpeta / "doc.md"
    doc.write_text("# doc", encoding="utf-8")
    png = bytes.fromhex("89504e470d0a1a0a")
    (carpeta / "propia.png").write_bytes(png)
    (carpeta / "medios" / "propia.png").write_bytes(png)
    (carpeta.parent / "vecina.png").write_bytes(png)

    api = main.WindowApi(main.App())
    api._docs["d"] = main.Doc(id="d", path=doc)

    def data(src, override=False):
        return api.image_data("d", src, override)

    check("una imagen de la carpeta del documento se carga",
          data("propia.png").get("ok"))
    check("una imagen de una subcarpeta se carga",
          data("medios/propia.png").get("ok"))

    fuera = [
        ("relativa hacia arriba", "../vecina.png"),
        ("codificada", "%2e%2e%2fvecina.png"),
        ("mezclada", "..%2fvecina.png"),
        ("absoluta", str(carpeta.parent / "vecina.png")),
    ]
    for nombre, src in fuera:
        res = data(src)
        check(f"queda fuera: {nombre}", not res.get("ok") and res.get("reason") == "fuera", res)

    red = [
        ("UNC", r"\\servidor.example\recurso\x.png"),
        ("UNC con barras normales", "//servidor.example/recurso/x.png"),
        ("ruta de dispositivo", r"\\?\C:\x.png"),
        ("dispositivo punto", r"\\.\C:\x.png"),
    ]
    for nombre, src in red:
        res = data(src)
        check(f"se rechaza por red: {nombre}",
              not res.get("ok") and res.get("reason") == "red", res)
        res2 = data(src, override=True)
        check(f"el permiso del usuario no levanta la red: {nombre}",
              not res2.get("ok") and res2.get("reason") == "red", res2)

    res = data("propia.png:oculto")
    check("se rechaza un flujo alternativo de NTFS", not res.get("ok"), res)

    # Con el permiso dado, una imagen local fuera de la carpeta sí se carga:
    # es la puerta que deja la configuración avanzada.
    check("con permiso explícito se carga una imagen local de más arriba",
          data("../vecina.png", override=True).get("ok"))

    # Una carpeta de confianza levanta la contención sin permiso por imagen.
    api._app.settings["trusted_dirs"] = [str(carpeta.parent)]
    check("una carpeta de confianza permite la imagen vecina",
          data("../vecina.png").get("ok"))
    api._app.settings["trusted_dirs"] = []

    # Los enlaces del documento nunca salen del equipo.
    res = api.open_into("d", r"\\servidor.example\recurso\otro.md", True)
    check("un enlace del documento a una ruta UNC no se abre", not res.get("ok"), res)
    # Un archivo que el usuario eligió a mano no pasa por la contención.
    check("un archivo elegido por el usuario se abre igual",
          api.open_into("d2", str(doc)).get("ok") is not False)

    # Y el mismo corpus, ya renderizado, no debe dejar ninguna imagen cargada.
    cargar(w, "traversal.md")
    cargadas = w.evaluate_js(
        "[...document.querySelectorAll('#preview img[src]')]"
        ".filter((i) => i.getAttribute('src').startsWith('data:')).length")
    check("ninguna imagen fuera de la carpeta llega a la vista", cargadas == 0, cargadas)


def run_checks(window):
    try:
        if not wait_until(window, "window.appReady === true", 30):
            check("la aplicación arranca", False)
            return
        print("\n--- Rutas y contención ---")
        check_traversal(window)
        print("\n--- HTML activo ---")
        check_xss(window)
        print("\n--- Protocolos de URL ---")
        check_protocolos(window)
        print("\n--- Peticiones de red ---")
        check_imagenes(window)
        print("\n--- Mermaid ---")
        check_mermaid(window)
        print("\n--- KaTeX ---")
        check_katex(window)
        print("\n--- Suplantación de elementos ---")
        check_clobbering(window)
        print("\n--- Contenido oculto ---")
        check_oculto(window)
        print("\n--- Frontmatter ---")
        check_frontmatter(window)
        print("\n--- Markdown defectuoso ---")
        check_defectuoso(window)
    except Exception as exc:  # noqa: BLE001
        failures.append(f"excepción: {exc}")
        print("  FALLA  excepción:", exc)
    finally:
        print("\n" + ("TODO OK" if not failures
                      else f"{len(failures)} FALLAS: {json.dumps(failures, ensure_ascii=False)}"))
        window.destroy()


def run():
    main.CONFIG = Path(tempfile.mkdtemp(prefix="visormd-sec-cfg-")) / "settings.json"
    api = main.WindowApi(main.App())
    window = webview.create_window("Seguridad", url=str(main.resource("web", "index.html")),
                                   js_api=api, width=1200, height=820, text_select=True,
                                   frameless=True, easy_drag=False)
    api.attach(window)
    api._force_close = True
    threading.Thread(target=run_checks, args=(window,), daemon=True).start()
    webview.start(gui="edgechromium")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
