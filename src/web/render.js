/* Conversión de Markdown a HTML y post-proceso del documento renderizado. */

window.Render = (function () {
  const anchor = window.markdownItAnchor;
  const taskLists = window.markdownitTaskLists || window.markdownItTaskLists;

  const md = window.markdownit({
    html: true,
    linkify: true,
    breaks: false,
    typographer: false,
  });

  if (anchor) md.use(anchor, { permalink: anchor.permalink.headerLink(), level: [1, 2, 3, 4, 5, 6] });
  if (window.markdownitFootnote) md.use(window.markdownitFootnote);
  if (window.markdownitDeflist) md.use(window.markdownitDeflist);
  if (taskLists) md.use(taskLists, { enabled: true, label: true, labelAfter: false });

  const esc = (s) => s.replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const isRemote = (src) => /^(https?:|\/\/)/i.test(src);

  /* Cabecera con el lenguaje y hueco para el boton de copiar. */
  md.renderer.rules.fence = (tokens, idx) => {
    const token = tokens[idx];
    const lang = (token.info || '').trim().split(/\s+/)[0].toLowerCase();
    const code = token.content;

    // El código del diagrama viaja como texto: DOMPurify descarta los
    // atributos que contengan "-->" y los diagramas estan llenos de flechas.
    if (lang === 'mermaid') {
      return `<div class="mermaid-block"><pre class="mermaid-src">${esc(code)}</pre></div>`;
    }
    let body;
    if (lang && window.hljs && hljs.getLanguage(lang)) {
      try {
        body = hljs.highlight(code, { language: lang, ignoreIllegals: true }).value;
      } catch (e) {
        body = esc(code);
      }
    } else {
      body = esc(code);
    }
    return `<div class="codeblock">
  <div class="codeblock-head"><span>${esc(lang || 'texto')}</span></div>
  <pre><code class="hljs language-${esc(lang)}">${body}</code></pre>
</div>\n`;
  };

  /* Desplazar las tablas anchas dentro de su caja, nunca la pagina. */
  const openTable = md.renderer.rules.table_open;
  md.renderer.rules.table_open = (t, i, o, e, s) => (
    '<div class="table-wrap">' + (openTable ? openTable(t, i, o, e, s) : '<table>'));
  const closeTable = md.renderer.rules.table_close;
  md.renderer.rules.table_close = (t, i, o, e, s) => (
    (closeTable ? closeTable(t, i, o, e, s) : '</table>') + '</div>');

  /* Protocolos admitidos en cualquier URL del documento. Es una allowlist
     explícita en vez de la de DOMPurify, que además de estos acepta tel:,
     sms:, cid:, xmpp: y ftp:, que esta aplicación no usa. La alternativa
     final cubre las rutas relativas y las anclas, necesarias para las
     imágenes locales, los enlaces entre documentos y el índice. */
  const ALLOWED_URI = /^(?:https?:|mailto:|[#./?]|[^a-z]|[a-z+.\-]+(?:[^a-z+.\-:]|$))/i;

  /* Sanitiza el HTML generado antes de insertarlo: quita script, on*= y
     href=javascript:. style y form se prohiben aparte por ser globales. */
  const clean = (html) => (window.DOMPurify
    ? DOMPurify.sanitize(html, {
        ADD_ATTR: ['target', 'checked', 'disabled', 'id', 'open'],
        // Además de style y form, que son globales, se descartan los
        // elementos que traen un recurso externo por su cuenta: video, audio,
        // source, track y las imágenes de un SVG en línea piden la URL apenas
        // entran al DOM, antes de que ningún código pueda intervenir, y con
        // eso delatan la lectura del documento. No aportan nada al formato.
        FORBID_TAGS: ['style', 'form', 'video', 'audio', 'source', 'track',
                      'image', 'use'],
        FORBID_ATTR: ['autofocus', 'srcset', 'imagesrcset', 'ping', 'poster'],
        ALLOWED_URI_REGEXP: ALLOWED_URI,
      })
    : '');

  /* Segunda pasada para el SVG que genera Mermaid, que no atraviesa clean():
     lo entrega ya armado y se inserta con innerHTML. Mermaid sanea sus
     etiquetas por dentro, pero esta es la única vía por la que algo derivado
     del documento llega al DOM sin pasar por la frontera de la aplicación.
     Conserva <style>, que Mermaid acota con el id del diagrama y de donde
     sale todo el color; descarta foreignObject, la puerta de vuelta a HTML
     dentro de un SVG. */
  const cleanSvg = (svg) => (window.DOMPurify
    ? DOMPurify.sanitize(svg, {
        USE_PROFILES: { svg: true, svgFilters: true, html: true },
        ADD_TAGS: ['style'],
        FORBID_TAGS: ['foreignObject', 'script', 'form'],
        ALLOWED_URI_REGEXP: ALLOWED_URI,
      })
    : '');

  /* Ocultar el frontmatter YAML: es metadato, no contenido. */
  const stripFrontMatter = (text) => text.replace(
    /^---[ \t]*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)/, '');

  /* Impedir que un bloque de código esconda texto: lo que se copia debe ser
     exactamente lo que se ve. */
  function unhideCode(el) {
    el.querySelectorAll('pre [style], pre [hidden], code [style], code [hidden]')
      .forEach((n) => { n.removeAttribute('style'); n.removeAttribute('hidden'); });
  }

  /* Las imágenes remotas se descargan solo a pedido: cargarlas al abrir
     delata la IP y confirma la lectura del archivo. Las locales las entrega
     Python en base64, porque la interfaz corre sobre http://127.0.0.1 y
     Chromium no permite subrecursos file:// desde ese origen. */
  const MOTIVOS = {
    fuera: 'Imagen fuera de la carpeta del documento. Menú > Cargar imágenes bloqueadas.',
    red: 'Imagen en una ubicación de red: bloqueada siempre.',
    tipo: 'El archivo no es una imagen.',
    'tamaño': 'La imagen supera el tamaño máximo.',
    falta: 'No se encontró la imagen: ',
  };

  /* Quitar los recursos que trae un atributo style del documento.
     `background-image: url(...)` sale a la red apenas el elemento entra al
     DOM. Una ruta local tampoco funcionaría acá, porque la página vive en
     http://127.0.0.1 y no puede pedir subrecursos del disco, así que quitar
     la función url() no le saca nada al documento que hoy sirva. */
  function stripStyleUrls(el) {
    el.querySelectorAll('[style]').forEach((n) => {
      const css = n.getAttribute('style') || '';
      if (!/url\s*\(/i.test(css)) return;
      const limpio = css.replace(/url\s*\([^)]*\)/gi, 'none');
      if (limpio.trim()) n.setAttribute('style', limpio);
      else n.removeAttribute('style');
    });
  }

  function resolveImages(el, allowExternal, docId) {
    const api = window.pywebview && window.pywebview.api;
    el.querySelectorAll('img[src]').forEach((img) => {
      const src = img.getAttribute('src');
      if (src.startsWith('data:')) return;
      if (isRemote(src)) {
        if (allowExternal) return;
        img.removeAttribute('src');
        img.dataset.blocked = src;
        img.alt = 'Imagen remota bloqueada. Menú > Cargar imágenes bloqueadas.';
        return;
      }
      if (!api || !api.image_data || !docId) return;
      img.removeAttribute('src');
      // Una imagen local fuera de la carpeta del documento se trata igual que
      // una remota: se bloquea con aviso y el mismo permiso la carga.
      api.image_data(docId, src, !!allowExternal).then((res) => {
        if (res && res.ok) { img.src = res.uri; return; }
        const motivo = (res && res.reason) || 'falta';
        if (motivo === 'fuera' && !allowExternal) img.dataset.blocked = src;
        img.alt = (MOTIVOS[motivo] || MOTIVOS.falta) + (motivo === 'falta' ? src : '');
      }).catch(() => {});
    });
  }

  function addCopyButtons(el) {
    boxPlainPre(el);
    el.querySelectorAll('.codeblock').forEach((block) => {
      const head = block.querySelector('.codeblock-head');
      const code = block.querySelector('code');
      if (!head || !code || head.querySelector('.copy-btn')) return;
      const btn = document.createElement('button');
      btn.className = 'copy-btn';
      btn.type = 'button';
      btn.textContent = 'Copiar';
      btn.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(code.textContent);
          btn.textContent = 'Copiado';
          btn.classList.add('done');
          setTimeout(() => { btn.textContent = 'Copiar'; btn.classList.remove('done'); }, 1400);
        } catch (e) {
          btn.textContent = 'No se pudo copiar';
          setTimeout(() => { btn.textContent = 'Copiar'; }, 1400);
        }
      });
      head.appendChild(btn);
    });
  }

  /* Los bloques indentados con cuatro espacios no pasan por la regla fence:
     reciben la misma caja para tener también su boton de copiar. */
  function boxPlainPre(el) {
    el.querySelectorAll('pre').forEach((pre) => {
      if (pre.closest('.codeblock') || pre.closest('.mermaid-block')
          || pre.classList.contains('plain')) return;
      const box = document.createElement('div');
      box.className = 'codeblock';
      box.innerHTML = '<div class="codeblock-head"><span>texto</span></div>';
      pre.replaceWith(box);
      box.appendChild(pre);
    });
  }

  /* Alertas de GitHub: una cita que empieza por [!NOTE], [!TIP], [!IMPORTANT],
     [!WARNING] o [!CAUTION] se muestra como aviso con color e icono. */
  const ALERTS = {
    NOTE: 'Nota', TIP: 'Sugerencia', IMPORTANT: 'Importante',
    WARNING: 'Advertencia', CAUTION: 'Precaución',
  };

  function markAlerts(el) {
    el.querySelectorAll('blockquote').forEach((quote) => {
      const first = quote.firstElementChild;
      if (!first || first.tagName !== 'P') return;
      const m = first.textContent.match(/^\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*/i);
      if (!m) return;
      const kind = m[1].toUpperCase();
      quote.classList.add('alert', 'alert-' + kind.toLowerCase());
      const title = document.createElement('p');
      title.className = 'alert-title';
      title.textContent = ALERTS[kind];
      // Quitar el marcador del texto, conservando el resto del párrafo.
      first.childNodes.forEach((node) => {
        if (node.nodeType === Node.TEXT_NODE && node.nodeValue.includes('[!')) {
          node.nodeValue = node.nodeValue.replace(m[0], '');
        }
      });
      if (!first.textContent.trim() && !first.querySelector('img, code')) first.remove();
      quote.prepend(title);
    });
  }

  function markDoneTasks(el) {
    el.querySelectorAll('.task-list-item').forEach((li) => {
      const box = li.querySelector('input[type="checkbox"]');
      if (box) li.classList.toggle('done', box.checked);
    });
  }

  /* Regla de GitHub para $...$: sin espacios pegados a los delimitadores.
     Evita que un texto como "cuesta $5 y otro $10" se renderice como fórmula. */
  const INLINE_MATH = /\$(?![\s$])((?:[^$\\\n]|\\.)+?)(?<![\s\\])\$/g;

  function protectMath(el) {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (n.parentElement.closest('code, pre')
        ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
    });
    const nodes = [];
    let n;
    while ((n = walker.nextNode())) nodes.push(n);
    nodes.forEach((node) => {
      const out = node.nodeValue.replace(INLINE_MATH, (m, tex) => `\\(${tex}\\)`);
      if (out !== node.nodeValue) node.nodeValue = out;
    });
  }

  function renderMath(el) {
    if (!window.renderMathInElement) return;
    protectMath(el);
    try {
      renderMathInElement(el, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '\\[', right: '\\]', display: true },
          { left: '\\(', right: '\\)', display: false },
        ],
        ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code', 'option'],
        throwOnError: false,
        // trust queda en false, su valor por defecto: sin él, \href, \url y
        // \includegraphics quedan desactivados y una fórmula no puede navegar
        // ni cargar recursos.
        //
        // maxSize acota \rule y \kern, que sin techo aceptan tamaños como
        // 99999em y dejan la página inutilizable. 50em son unas cuarenta veces
        // el ancho de una línea: ninguna fórmula real se acerca.
        maxSize: 50,
        maxExpand: 1000,
      });
    } catch (e) { /* Fórmula inválida: conservar el texto original. */ }
  }

  /* Mermaid ocupa 3,5 MB: cargarlo solo si el documento trae diagramas. */
  let mermaidLoading = null;
  function loadMermaid() {
    if (window.mermaid) return Promise.resolve(window.mermaid);
    if (!mermaidLoading) {
      mermaidLoading = new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = 'vendor/mermaid.min.js';
        s.onload = () => resolve(window.mermaid);
        s.onerror = reject;
        document.head.appendChild(s);
      });
    }
    return mermaidLoading;
  }

  let mermaidSeq = 0;
  async function renderMermaid(el, theme, maxDiagrams) {
    const todos = el.querySelectorAll('.mermaid-block:has(.mermaid-src)');
    if (!todos.length) return;
    // Cada diagrama mide su propio SVG en el DOM, así que el coste crece con
    // la cantidad. Pasado el tope queda a la vista el código fuente, que es lo
    // que ya se muestra cuando mermaid no está disponible.
    const tope = maxDiagrams > 0 ? maxDiagrams : 50;
    const blocks = Array.from(todos).slice(0, tope);
    if (todos.length > tope) {
      for (const extra of Array.from(todos).slice(tope)) {
        const aviso = document.createElement('div');
        aviso.className = 'mermaid-error';
        aviso.textContent = `El documento supera los ${tope} diagramas; este no se dibujó.`;
        extra.prepend(aviso);
      }
    }
    let mermaid;
    try {
      mermaid = await loadMermaid();
      if (!mermaid) throw new Error('mermaid no disponible');
    } catch (e) {
      return;  // Sin mermaid queda visible el código fuente del diagrama.
    }
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: 'strict',
      // Las etiquetas se dibujan como texto SVG y no como HTML dentro de un
      // foreignObject. Con esto el diagrama no necesita meter HTML dentro del
      // SVG, que es justo lo que la segunda sanitización descarta: sin este
      // ajuste los rótulos de los nodos desaparecían.
      htmlLabels: false,
      flowchart: { htmlLabels: false },
      theme: theme === 'dark' ? 'dark' : 'default',
      darkMode: theme === 'dark',
      fontFamily: 'Segoe UI, system-ui, sans-serif',
      themeVariables: { primaryColor: '#1C9E1C', primaryTextColor: '#fff', lineColor: '#1C9E1C' },
    });
    for (const block of blocks) {
      const src = block.querySelector('.mermaid-src').textContent;
      // Sin contenedor propio, mermaid arma uno temporal en <body> para medir
      // el SVG y no siempre lo retira: al renderizar varias veces esos restos
      // se acumulan y quedan flotando sobre la página.
      const scratch = document.createElement('div');
      scratch.style.cssText = 'position:absolute;top:-9999px;left:-9999px;visibility:hidden;';
      document.body.appendChild(scratch);
      try {
        const { svg } = await mermaid.render('mmd-' + (++mermaidSeq), src, scratch);
        block.innerHTML = cleanSvg(svg);
      } catch (e) {
        block.innerHTML = '<div class="mermaid-error">Diagrama Mermaid inválido: '
          + esc(String(e && e.message ? e.message : e)) + '</div>';
      } finally {
        scratch.remove();
      }
    }
  }

  function buildToc(el, listEl) {
    listEl.innerHTML = '';
    const heads = el.querySelectorAll('h1[id], h2[id], h3[id], h4[id], h5[id], h6[id]');
    heads.forEach((h) => {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.href = '#' + h.id;
      a.textContent = h.textContent.replace(/\s*#\s*$/, '');
      a.dataset.level = h.tagName[1];
      a.dataset.target = h.id;
      li.appendChild(a);
      listEl.appendChild(li);
    });
    return heads;
  }

  /** Renderizar `text` dentro de `el`. Devuelve una promesa: mermaid es asíncrono. */
  function render(text, el, opts) {
    const o = opts || {};
    el.innerHTML = clean(md.render(stripFrontMatter(text || '')));
    // Estas dos van antes que nada y sin esperar a nadie: el navegador pide
    // los recursos del HTML recién insertado en cuanto termina este bloque de
    // código, así que lo que no se quite ahora ya salió a la red.
    stripStyleUrls(el);
    resolveImages(el, o.remoteImages, o.docId);
    unhideCode(el);
    addCopyButtons(el);
    markAlerts(el);
    markDoneTasks(el);
    renderMath(el);
    return renderMermaid(el, o.theme, o.maxDiagrams);
  }

  /** Mostrar texto plano sin interpretar. */
  function renderPlain(text, el) {
    el.innerHTML = '<pre class="plain"><code></code></pre>';
    el.querySelector('code').textContent = text || '';
  }

  return { md, render, renderPlain, buildToc };
})();
