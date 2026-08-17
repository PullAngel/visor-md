"""Prueba de humo: abre la app real, revisa el render y las ayudas de edición.

    python tests/smoke.py

Falla ruidosamente si el documento no se renderiza como corresponde.
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

SAMPLE = ROOT / "tests" / "muestra.md"
CHECKS = """(() => {
  const q = (s) => document.querySelectorAll(s).length;
  return {
    editorLen: document.getElementById('editor').value.length,
    h2: q('#preview h2'),
    headingAnchor: q('#preview h2 a[href^="#"]'),
    codeblocks: q('.codeblock'),
    copyBtns: q('.copy-btn'),
    hljs: q('#preview .hljs-keyword'),
    tables: q('#preview table'),
    tableWrap: q('.table-wrap'),
    tasks: q('.task-list-item'),
    tasksDone: q('.task-list-item-checkbox:checked'),
    katex: q('#preview .katex'),
    mermaid: q('.mermaid-block svg'),
    mermaidError: document.querySelector('.mermaid-error')?.textContent || '',
    toc: q('#toc-list a'),
    footnotes: q('.footnotes'),
    deflist: q('#preview dl'),
    kbd: document.querySelectorAll('#preview kbd').length,
    mode: document.getElementById('switch').dataset.mode,
    ocultos: ['fmtbar', 'findbar', 'dialog', 'menu', 'editor']
      .filter((id) => document.getElementById(id).offsetParent !== null
                      || getComputedStyle(document.getElementById(id)).display !== 'none'),
  };
})()"""

EDIT_CHECKS = """(() => {
  const ta = document.getElementById('editor');
  const out = {};
  const run = (text, sel, kind) => {
    ta.value = ''; ta.focus();
    document.execCommand('insertText', false, text);
    ta.setSelectionRange(sel[0], sel[1]);
    Editor.apply(kind);
    return ta.value;
  };
  out.bold = run('hola mundo', [0, 4], 'bold');
  out.unbold = (() => { ta.value=''; ta.focus();
    document.execCommand('insertText', false, '**hola** mundo');
    ta.setSelectionRange(0, 8); Editor.apply('bold'); return ta.value; })();
  out.task = run('comprar pan', [0, 0], 'task');
  out.quote = run('una cita', [0, 0], 'quote');
  out.ol = run('uno\\ndos\\ntres', [0, 12], 'ol');
  out.link = run('Anthropic', [0, 9], 'link');
  out.enterList = (() => {
    ta.value = ''; ta.focus();
    document.execCommand('insertText', false, '- primero');
    ta.setSelectionRange(9, 9);
    ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
    return ta.value;
  })();
  out.exitList = (() => {
    ta.value = ''; ta.focus();
    document.execCommand('insertText', false, '- ');
    ta.setSelectionRange(2, 2);
    ta.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true}));
    return JSON.stringify(ta.value);
  })();
  return out;
})()"""

EXPECTED_EDIT = {
    "bold": "**hola** mundo",
    "unbold": "hola mundo",
    "task": "- [ ] comprar pan",
    "quote": "> una cita",
    "ol": "1. uno\n2. dos\n3. tres",
    "link": "[Anthropic](url)",
    "enterList": "- primero\n- ",
    "exitList": '""',
}

failures = []


def new_api(path=None):
    """Una ventana de prueba con su propio estado compartido."""
    return main.WindowApi(main.App(), initial_path=path)


def check(name, ok, detail=""):
    print(("  OK   " if ok else "  FALLA") + f"  {name}" + (f"  -> {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def wait_until(window, expression, timeout=25):
    """Esperar a que una expresión JavaScript sea verdadera, sin dormir a ciegas."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if window.evaluate_js(expression):
                return True
        except Exception:  # noqa: BLE001  (la ventana todavía no responde)
            pass
        time.sleep(0.25)
    return False


def wait_ready(window, timeout=25):
    """Esperar a que la interfaz arranque, se dibuje y termine los diagramas.

    Una ventana recién mostrada tarda un instante en tener medidas: sin
    esperarlas, cualquier comprobación de scroll o de tamaño lee ceros.
    """
    if not wait_until(window, "window.appReady === true", timeout):
        return False
    wait_until(window, "document.getElementById('preview').clientHeight > 0", 10)
    wait_until(window, "document.querySelectorAll('.mermaid-block').length === 0"
                       " || document.querySelector('.mermaid-block svg, .mermaid-error')"
                       " !== null", 20)
    return True


ESTRES = """({
  frontmatter: document.getElementById('preview').textContent.includes('tags: [markdown'),
  anidadas4: document.querySelectorAll('#preview ul ul ul ul').length,
  olEnUl: document.querySelectorAll('#preview ul ol').length,
  olStart5: !!document.querySelector('#preview ol[start="5"]'),
  tablas: document.querySelectorAll('#preview table').length,
  fenceEnLista: document.querySelectorAll('#preview li .codeblock').length,
  brEnTabla: document.querySelectorAll('#preview table br').length,
  enlaceRef: !!document.querySelector('#preview a[href*="daringfireball"]'),
  html: ['b', 'mark', 'kbd', 'div[align]', 'details', 'summary']
        .filter((s) => !document.querySelector('#preview ' + s)),
  pwned: [!!window.__PWNED, !!window.__PWNED2, !!window.__PWNED3],
  peligroso: ['script', '[onerror]', 'a[href^="javascript"]', 'form']
        .filter((s) => document.querySelector('#preview ' + s))
        // el <style> del SVG de Mermaid es propio y está acotado con #mmd-N
        .concat([...document.querySelectorAll('#preview style')]
                .some((s) => !s.closest('.mermaid-block')) ? ['style'] : []),
  tareas: document.querySelectorAll('#preview input[type=checkbox]').length,
  setextH1: document.querySelectorAll('#preview h1').length,
  escapes: document.getElementById('preview').textContent.includes('*no es cursiva*'),
  mdLiteral: (document.querySelector('.language-markdown')||{}).textContent||'',
  fence4: [...document.querySelectorAll('.codeblock code')]
          .filter((c) => c.textContent.includes('```python')).length,
  tildes: [...document.querySelectorAll('.codeblock code')]
          .filter((c) => c.textContent.includes('con_tildes')).length,
  notas: document.querySelectorAll('.footnotes li').length,
  autolinks: ['a[href*="query=1"]', 'a[href^="mailto"]', 'a[href*="anthropic.com/news"]']
        .filter((s) => !document.querySelector('#preview ' + s)),
  katex: document.querySelectorAll('#preview .katex').length,
  precios: document.getElementById('preview').textContent.includes('cuesta $5 y el otro $10'),
  mermaidOk: document.querySelectorAll('.mermaid-block svg').length,
  mermaidErr: document.querySelectorAll('.mermaid-error').length,
  plantillas: document.getElementById('preview').textContent.includes('{{ variable }}'),
  citaCodigo: document.querySelectorAll('#preview blockquote .codeblock').length,
  sinCaja: [...document.querySelectorAll('#preview pre')]
        .filter((p) => !p.closest('.codeblock') && !p.closest('.mermaid-block')).length,
  copiar: document.querySelectorAll('.copy-btn').length,
  bloques: document.querySelectorAll('.codeblock').length,
  copiaOculta: [...document.querySelectorAll('.codeblock code')]
        .filter((c) => !c.closest('details:not([open])')
                       && c.textContent.trim() !== (c.innerText || '').trim()).length,
  estilosEnCodigo: document.querySelectorAll('.codeblock [style], .codeblock [hidden]').length,
  imagenLocal: [...document.querySelectorAll('#preview img')]
        .some((i) => i.naturalWidth > 0),
  imagenRemotaBloqueada: document.querySelectorAll('#preview img[data-blocked]').length,
  alertas: [...document.querySelectorAll('#preview .alert-title')].map((t) => t.textContent),
  citaNormal: document.querySelectorAll('#preview blockquote:not(.alert)').length,
  marcadorAlerta: document.getElementById('preview').textContent.includes('[!NOTE]'),
  overlayContenido: (() => {
    const o = document.getElementById('overlay-hostil');
    if (!o) return 'sin capa de prueba';
    const r = o.getBoundingClientRect();
    const t = document.getElementById('toolbar').getBoundingClientRect();
    return r.top >= t.bottom ? 'confinada' : 'cubre la barra';
  })(),
})"""


def check_estres():
    """Los 26 casos raros de tests/estres.md, incluida la sanitización."""
    api = new_api(str(ROOT / "tests" / "estres.md"))
    w = webview.create_window("Smoke estrés", url=str(main.resource("web", "index.html")),
                              js_api=api, width=1200, height=820, hidden=True, text_select=True)
    api.attach(w)
    api._shown = True      # ventana de prueba: no mostrarla
    api._force_close = True  # cerrar sin preguntar por cambios sin guardar
    try:
        if not wait_ready(w):
            check("estres.md abre", False)
            return
        wait_until(w, "document.querySelectorAll('#preview img[data-blocked]').length > 0", 10)
        r = w.evaluate_js(ESTRES)
        check("frontmatter YAML oculto", not r["frontmatter"])
        check("listas anidadas de 4 niveles", r["anidadas4"] >= 1)
        check("numerada dentro de viñeta", r["olEnUl"] >= 1)
        check("lista que arranca en 5", r["olStart5"])
        check("tablas", r["tablas"] == 3, r["tablas"])
        check("bloque de código dentro de lista", r["fenceEnLista"] == 2, r["fenceEnLista"])
        check("<br> dentro de tabla", r["brEnTabla"] >= 1)
        check("enlace de referencia", r["enlaceRef"])
        check("HTML (b, mark, kbd, div, details, summary)", not r["html"], ", ".join(r["html"]))
        check("NO ejecuta scripts inyectados", not any(r["pwned"]), str(r["pwned"]))
        check("elimina script/onerror/javascript:/style/form", not r["peligroso"],
              ", ".join(r["peligroso"]))
        check("checkboxes", r["tareas"] == 4, r["tareas"])
        check("encabezados setext", r["setextH1"] == 2, r["setextH1"])
        check("escapes con barra invertida", r["escapes"])
        check("Markdown dentro de código queda literal",
              r["mdLiteral"].startswith("# Este título no debe renderizarse"))
        check("valla de 4 backticks con ``` adentro", r["fence4"] == 1, r["fence4"])
        check("bloques con ~~~", r["tildes"] == 1, r["tildes"])
        check("footnotes", r["notas"] == 2, r["notas"])
        check("autolinks (<>, mailto, bare)", not r["autolinks"], ", ".join(r["autolinks"]))
        check("LaTeX: 3 fórmulas y ni una de más", r["katex"] == 3, r["katex"])
        check("LaTeX NO se come '$5 y $10'", r["precios"])
        check("Mermaid válido renderiza", r["mermaidOk"] == 1)
        check("Mermaid inválido muestra el error", r["mermaidErr"] == 1)
        check("plantillas {{ }} intactas", r["plantillas"])
        check("código dentro de cita", r["citaCodigo"] == 1)
        check("todo bloque tiene caja y botón Copiar",
              r["sinCaja"] == 0 and r["copiar"] == r["bloques"],
              f'{r["sinCaja"]} sueltos, {r["copiar"]}/{r["bloques"]} botones')
        check("se copia exactamente lo que se ve",
              r["copiaOculta"] == 0 and r["estilosEnCodigo"] == 0,
              f'{r["copiaOculta"]} bloques distintos, {r["estilosEnCodigo"]} con estilo')
        check("las imágenes locales cargan", r["imagenLocal"])
        check("las imágenes remotas quedan bloqueadas", r["imagenRemotaBloqueada"] >= 1,
              r["imagenRemotaBloqueada"])
        check("el documento no puede cubrir la barra", r["overlayContenido"] == "confinada",
              r["overlayContenido"])
        check("las 5 alertas de GitHub se renderizan",
              r["alertas"] == ["Nota", "Sugerencia", "Importante", "Advertencia", "Precaución"],
              ", ".join(r["alertas"]))
        check("el marcador [!NOTE] no queda a la vista", not r["marcadorAlerta"])
        check("una cita sin marcador sigue siendo cita",
              r["citaNormal"] >= 2, r["citaNormal"])

        # Repetir el render (como pasa varias veces al cambiar de pestaña o
        # de tema) no debe ir dejando restos de Mermaid sueltos en <body>.
        w.evaluate_js("document.getElementById('btn-theme').click()")
        wait_until(w, "document.querySelectorAll('.mermaid-block svg, .mermaid-error').length"
                      " === 2", 10)
        w.evaluate_js("document.getElementById('btn-theme').click()")
        wait_until(w, "document.querySelectorAll('.mermaid-block svg, .mermaid-error').length"
                      " === 2", 10)
        restos = w.evaluate_js("[...document.body.children]"
                               ".filter((c) => c.id !== 'preview' && /^d?mmd-/.test(c.id || ''))"
                               ".length")
        check("re-renderizar no deja restos de Mermaid en <body>", restos == 0, restos)
    finally:
        w.destroy()


def check_txt():
    """Un .txt abre en modo edición, sin interpretar, y ofrece pasarlo a .md."""
    txt = Path(tempfile.mkdtemp(prefix="visormd-txt-")) / "notas.txt"
    txt.write_text("Lista del super\n\n- pan\n- cafe\n", encoding="utf-8")
    api = new_api(str(txt))
    w = webview.create_window("Smoke .txt", url=str(main.resource("web", "index.html")),
                              js_api=api, width=900, height=600, hidden=True, text_select=True)
    api.attach(w)
    api._shown = True      # ventana de prueba: no mostrarla
    api._force_close = True  # cerrar sin preguntar por cambios sin guardar
    try:
        if not wait_ready(w):
            check("el .txt abre la ventana", False)
            return
        r = w.evaluate_js("""({
          mode: document.getElementById('switch').dataset.mode,
          plano: !!document.querySelector('#preview pre.plain'),
          botonInterpretar: !document.getElementById('btn-plain').hidden,
          convertirAMd: !document.querySelector('#menu [data-act="tomd"]').hidden,
          texto: document.getElementById('editor').value,
        })""")
        check("abre en modo edición", r["mode"] == "edit", r["mode"])
        check("no interpreta el .txt como Markdown", r["plano"])
        check("ofrece 'Interpretar como Markdown'", r["botonInterpretar"])
        check("ofrece 'Convertir a .md'", r["convertirAMd"])
        check("carga el contenido intacto", r["texto"] == "Lista del super\n\n- pan\n- cafe\n")
    finally:
        w.destroy()


def check_tabs():
    """Varias pestañas en una sola ventana: abrir, cambiar, marcar sucia y cerrar."""
    api = new_api(str(SAMPLE))
    w = webview.create_window("Smoke pestañas", url=str(main.resource("web", "index.html")),
                              js_api=api, width=1100, height=780, hidden=True, text_select=True)
    api.attach(w)
    api._shown = True
    api._force_close = True
    try:
        if not wait_ready(w):
            check("la ventana de pestañas arranca", False)
            return

        r1 = w.evaluate_js("({count: document.querySelectorAll('.tab').length,"
                           " activo: document.querySelector('.tab.active .tab-name').textContent})")
        check("arranca con una sola pestaña", r1["count"] == 1, r1["count"])
        check("la pestaña muestra el nombre del archivo", r1["activo"] == "muestra.md", r1["activo"])

        # evaluate_js no espera promesas: solo serializa el valor inmediato,
        # que para una función async es la Promise pendiente ("{}"). Se
        # dispara sin esperar la respuesta y se sondea el DOM por separado.
        estres = str(ROOT / "tests" / "estres.md")
        w.evaluate_js(f"window.__openExternalTab({json.dumps(estres)})")
        # El conteo de pestañas cambia enseguida (síncrono); el contenido del
        # archivo llega después por el puente con Python. Se espera lo segundo.
        wait_until(w, "(document.querySelector('.tab.active .tab-name')||{}).textContent"
                      " === 'estres.md'", 10)
        r2 = w.evaluate_js("""({
          count: document.querySelectorAll('.tab').length,
          activo: document.querySelector('.tab.active .tab-name').textContent,
          h1: (document.querySelector('#preview h1')||{}).textContent||'',
        })""")
        check("abrir un segundo archivo agrega una pestaña", r2["count"] == 2, r2["count"])
        check("la pestaña nueva queda activa", r2["activo"] == "estres.md", r2["activo"])
        check("el contenido corresponde al segundo archivo",
              "Estrés" in r2["h1"], r2["h1"])

        # La pestaña cambia en pointerdown, como en un navegador: .click() ya
        # no alcanza, hay que simular el puntero de verdad.
        r3 = w.evaluate_js("""(() => {
          const el = document.querySelectorAll('.tab')[0];
          const r = el.getBoundingClientRect();
          const at = { bubbles: true, button: 0, pointerId: 1, isPrimary: true,
                       clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 };
          el.dispatchEvent(new PointerEvent('pointerdown', at));
          el.dispatchEvent(new PointerEvent('pointerup', at));
          return document.querySelector('#preview h1').textContent;
        })()""")
        check("clic en la primera pestaña vuelve a mostrar su documento",
              "prueba de Visor MD" in r3, r3)

        w.evaluate_js("""(() => {
          const ta = document.getElementById('editor');
          document.getElementById('mode-edit').click();
          ta.focus();
          document.execCommand('insertText', false, ' más texto');
        })()""")
        time.sleep(0.2)
        r4 = w.evaluate_js("!document.querySelector('.tab.active .tab-dirty').hidden")
        check("escribir marca la pestaña como sucia", r4)

        # Guardar una pestaña que no está a la vista debe escribir SU texto.
        # Antes se guardaba el contenido del editor visible, de modo que una
        # pestaña nueva vacía dejaba en cero el archivo de la otra pestaña.
        victima = Path(tempfile.mkdtemp(prefix="visormd-fondo-")) / "fondo.md"
        victima.write_text("# Contenido original\n", encoding="utf-8")
        w.evaluate_js(f"window.__openExternalTab({json.dumps(str(victima))})")
        wait_until(w, "(document.querySelector('.tab.active .tab-name')||{}).textContent"
                      " === 'fondo.md'", 10)
        w.evaluate_js("""(() => {
          const el = document.querySelectorAll('.tab')[0];
          const r = el.getBoundingClientRect();
          const at = { bubbles: true, button: 0, pointerId: 1, isPrimary: true,
                       clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 };
          el.dispatchEvent(new PointerEvent('pointerdown', at));
          el.dispatchEvent(new PointerEvent('pointerup', at));
          document.getElementById('editor').value = '';
        })()""")
        time.sleep(0.3)
        w.evaluate_js("window.__saveByName && window.__saveByName('fondo.md')")
        time.sleep(0.6)
        check("guardar una pestaña de fondo no la vacía",
              victima.read_text(encoding="utf-8").startswith("# Contenido original"),
              repr(victima.read_text(encoding="utf-8")[:30]))
        w.evaluate_js("""(() => {
          const tabs = [...document.querySelectorAll('.tab')];
          const t = tabs.find((x) => x.textContent.includes('fondo.md'));
          if (t) t.querySelector('.tab-close').click();
        })()""")
        time.sleep(0.4)

        w.evaluate_js("document.querySelector('.tab.active .tab-close').click()")
        time.sleep(0.2)
        w.evaluate_js("document.getElementById('dlg-ok').click()")
        time.sleep(0.3)
        r5 = w.evaluate_js("({count: document.querySelectorAll('.tab').length,"
                           " activo: document.querySelector('.tab.active .tab-name').textContent})")
        check("cerrar la pestaña sucia pide confirmación y la quita",
              r5["count"] == 1, r5["count"])
        check("queda activa la pestaña restante", r5["activo"] == "estres.md", r5["activo"])
    finally:
        w.destroy()


def check_menu_contextual(w):
    """Menú del clic derecho. Necesita una ventana visible: una oculta no
    mantiene la selección de texto del documento."""
    ctx = w.evaluate_js("""(() => {
      const p = document.querySelector('#preview p');
      const r = document.createRange();
      r.selectNodeContents(p);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r);
      const box = p.getBoundingClientRect();
      p.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true,
        clientX: box.left + 40, clientY: box.top + 6}));
      return {
        visible: !document.getElementById('ctxmenu').hidden,
        seleccion: String(getSelection()).trim().slice(0, 30),
        items: [...document.querySelectorAll('#ctxmenu button span')].map((x) => x.textContent),
      };
    })()""")
    check("el clic derecho abre un menú", ctx["visible"])
    check("con texto seleccionado ofrece copiar",
          any(i == "Copiar" for i in ctx["items"]),
          f'selección {ctx["seleccion"]!r}: ' + ", ".join(ctx["items"]))
    check("y ofrece buscar la selección",
          any(i.startswith("Buscar") for i in ctx["items"]))

    ctx2 = w.evaluate_js("""(() => {
      getSelection().removeAllRanges();
      const b = document.querySelector('.codeblock code');
      const box = b.getBoundingClientRect();
      b.dispatchEvent(new MouseEvent('contextmenu', {bubbles: true,
        clientX: box.left + 10, clientY: box.top + 6}));
      return [...document.querySelectorAll('#ctxmenu button span')].map((x) => x.textContent);
    })()""")
    check("sobre un bloque de código ofrece copiarlo",
          any("bloque de código" in i for i in ctx2), ", ".join(ctx2))
    w.evaluate_js("document.getElementById('ctxmenu').hidden = true")


def check_interfaz():
    """Desbordamiento de la barra de pestañas y su selector."""
    api = new_api(str(ROOT / "tests" / "muestra.md"))
    w = webview.create_window("Smoke interfaz", url=str(main.resource("web", "index.html")),
                              js_api=api, width=900, height=620, hidden=True,
                              frameless=True, easy_drag=False, text_select=True)
    api.attach(w)
    api._force_close = True
    try:
        if not wait_ready(w):
            check("la ventana de interfaz arranca", False)
            return

        # El selector aparece solo cuando las pestañas ya no entran.
        antes = w.evaluate_js("!document.getElementById('btn-tablist').hidden")
        for _ in range(14):
            w.evaluate_js("window.__newTabForTest && window.__newTabForTest()")
        wait_until(w, "document.querySelectorAll('.tab').length >= 12", 10)
        time.sleep(0.5)
        despues = w.evaluate_js("!document.getElementById('btn-tablist').hidden")
        check("sin desbordar, no aparece el selector de pestañas", not antes)
        check("con muchas pestañas aparece el selector", despues)
        lista = w.evaluate_js("""(() => {
          document.getElementById('btn-tablist').click();
          return document.querySelectorAll('#tablist button').length;
        })()""")
        check("el selector lista todas las pestañas abiertas", lista >= 12, lista)
        w.evaluate_js("document.getElementById('tablist').hidden = true")
    finally:
        w.destroy()


def check_scroll_y_borrador(w):
    """El punto de lectura se conserva al cambiar de modo y el borrador se nombra solo.

    Va sobre la ventana principal: medir scroll necesita una ventana dibujada.
    """
    largo = Path(tempfile.mkdtemp(prefix="visormd-scroll-")) / "largo.md"
    largo.write_text("# Documento largo\n\n" + "\n\n".join(
        f"## Sección {i}\n\nTexto de relleno de la sección {i}." for i in range(1, 60)),
        encoding="utf-8")
    w.evaluate_js(f"window.__openExternalTab({json.dumps(str(largo))})")
    wait_until(w, "(document.querySelector('.tab.active .tab-name')||{}).textContent"
                  " === 'largo.md'", 10)
    wait_until(w, "document.getElementById('preview').scrollHeight >"
                  " document.getElementById('preview').clientHeight", 10)

    antes = w.evaluate_js("""(() => {
      const p = document.getElementById('preview');
      p.scrollTop = (p.scrollHeight - p.clientHeight) * 0.5;
      return { alto: p.scrollHeight, visible: p.clientHeight, top: p.scrollTop };
    })()""")
    time.sleep(0.4)
    check("la vista de lectura tiene scroll", antes["top"] > 0, str(antes))
    w.evaluate_js("document.getElementById('mode-edit').click()")
    time.sleep(0.8)
    pos = w.evaluate_js("""(() => {
      const e = document.getElementById('editor');
      const max = e.scrollHeight - e.clientHeight;
      return { ratio: max > 0 ? e.scrollTop / max : 0, cursor: e.selectionStart,
               total: e.value.length };
    })()""")
    check("al pasar a edición se conserva el punto de lectura",
          0.25 <= pos["ratio"] <= 0.75, f'proporción {pos["ratio"]:.2f}')
    check("el cursor acompaña al punto de lectura",
          0 < pos["cursor"] < pos["total"], f'{pos["cursor"]} de {pos["total"]}')

    # Una pestaña nueva toma su nombre del contenido.
    w.evaluate_js("window.__newTabForTest && window.__newTabForTest()")
    time.sleep(0.5)
    w.evaluate_js("""(() => {
      const ta = document.getElementById('editor');
      ta.focus();
      document.execCommand('insertText', false, '# Notas de la reunión\\n\\ntexto');
    })()""")
    wait_until(w, "document.querySelector('.tab.active .tab-name').textContent"
                  " !== 'Sin título'", 5)
    nombre = w.evaluate_js("document.querySelector('.tab.active .tab-name').textContent")
    check("la pestaña sin guardar se nombra por su contenido",
          nombre == "Notas de la reunión", nombre)
    check("y se distingue de un archivo real",
          w.evaluate_js("!!document.querySelector('.tab.active.draft')"))


def check_close_dialog():
    """Cerrar con cambios sin guardar avisa con el diálogo propio, no con el de Windows."""
    doc = Path(tempfile.mkdtemp(prefix="visormd-cierre-")) / "pendiente.md"
    doc.write_text("# Sin guardar\n", encoding="utf-8")
    api = new_api(str(doc))
    w = webview.create_window("Smoke cierre", url=str(main.resource("web", "index.html")),
                              js_api=api, width=900, height=600, hidden=True, text_select=True)
    api.attach(w)
    api._shown = True
    cerrada = threading.Event()
    w.events.closed += cerrada.set
    try:
        if not wait_ready(w):
            check("la ventana de cierre arranca", False)
            return
        w.evaluate_js("""(() => {
          const ta = document.getElementById('editor');
          document.getElementById('mode-edit').click();
          ta.focus();
          document.execCommand('insertText', false, 'cambio sin guardar');
        })()""")
        wait_until(w, "!document.querySelector('.tab.active .tab-dirty').hidden", 5)

        # Cerrar como lo haría el botón X de la ventana.
        w.destroy()
        aparecio = wait_until(w, "document.getElementById('dialog').hidden === false", 8)
        check("el aviso de cierre es el de la aplicación", aparecio)
        if aparecio:
            texto = w.evaluate_js("document.getElementById('dlg-body').textContent")
            check("el aviso nombra la pestaña sin guardar", "pendiente.md" in texto,
                  texto.strip()[:60])
            check("la ventana sigue abierta mientras se pregunta",
                  w.evaluate_js("1 + 1") == 2 and not cerrada.is_set())
            # Confirmar el cierre desde el propio diálogo.
            w.evaluate_js("document.getElementById('dlg-ok').click()")
            check("confirmar en el diálogo cierra la ventana", cerrada.wait(6))
    finally:
        api._force_close = True
        try:
            w.destroy()
        except Exception:
            pass


def run_checks(window):
    if not wait_ready(window):
        failures.append("la app no terminó de arrancar")
        print("  FALLA  la app no terminó de arrancar")
        window.destroy()
        return
    try:
        r = window.evaluate_js(CHECKS)
        print("\n--- Render ---")
        check("documento cargado en el editor", r["editorLen"] > 2000, r["editorLen"])
        check("encabezados h2", r["h2"] >= 8, r["h2"])
        check("anclas en encabezados", r["headingAnchor"] >= 8, r["headingAnchor"])
        check("bloques de código", r["codeblocks"] == 5, r["codeblocks"])
        check("botones de copiar", r["copyBtns"] == 5, r["copyBtns"])
        check("resaltado de sintaxis", r["hljs"] >= 3, r["hljs"])
        check("tabla con scroll propio", r["tables"] == 1 and r["tableWrap"] == 1)
        check("lista de tareas", r["tasks"] == 4 and r["tasksDone"] == 2,
              f'{r["tasks"]} tareas / {r["tasksDone"]} hechas')
        check("fórmulas KaTeX", r["katex"] >= 2, r["katex"])
        check("diagrama Mermaid", r["mermaid"] == 1, r["mermaidError"] or r["mermaid"])
        check("índice lateral", r["toc"] >= 10, r["toc"])
        check("notas al pie", r["footnotes"] == 1)
        check("lista de definiciones", r["deflist"] == 1)
        check("HTML inline renderizado (<kbd>)", r["kbd"] == 1, r["kbd"])
        check("arranca en modo lectura", r["mode"] == "read", r["mode"])
        check("paneles ocultos en lectura", not r["ocultos"], ", ".join(r["ocultos"]))

        print("\n--- Casos de estrés y sanitización ---")
        check_estres()

        print("\n--- Archivos .txt ---")
        check_txt()

        print("\n--- Pestañas ---")
        check_tabs()

        print("\n--- Menú del clic derecho ---")
        check_menu_contextual(window)

        print("\n--- Barra de pestañas ---")
        check_interfaz()

        print("\n--- Scroll entre modos y borradores ---")
        check_scroll_y_borrador(window)

        print("\n--- Aviso de cierre ---")
        check_close_dialog()

        print("\n--- Ayudas de edición ---")
        window.evaluate_js("document.getElementById('mode-edit').click()")
        time.sleep(0.4)
        e = window.evaluate_js(EDIT_CHECKS)
        for key, expected in EXPECTED_EDIT.items():
            check(key, e[key] == expected, f"esperado {expected!r}, obtenido {e[key]!r}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"excepción: {exc}")
        print("  FALLA  excepción:", exc)
    finally:
        print("\n" + ("TODO OK" if not failures
                      else f"{len(failures)} FALLAS: {json.dumps(failures, ensure_ascii=False)}"))
        window.destroy()


def run():
    # Ajustes propios y descartables: la prueba no debe depender de (ni pisar)
    # las preferencias reales del usuario.
    main.CONFIG = Path(tempfile.mkdtemp(prefix="visormd-test-")) / "settings.json"
    api = new_api(str(SAMPLE))
    window = webview.create_window("Smoke test", url=str(main.resource("web", "index.html")),
                                   js_api=api, width=1200, height=820, text_select=True,
                                   frameless=True, easy_drag=False)
    api.attach(window)
    api._force_close = True  # cerrar sin preguntar por cambios sin guardar
    threading.Thread(target=run_checks, args=(window,), daemon=True).start()
    webview.start(gui="edgechromium")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
