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

  /* Sanitiza el HTML generado antes de insertarlo: quita script, on*= y
     href=javascript:. style y form se prohiben aparte por ser globales. */
  const clean = (html) => (window.DOMPurify
    ? DOMPurify.sanitize(html, {
        ADD_ATTR: ['target', 'checked', 'disabled', 'id', 'open'],
        FORBID_TAGS: ['style', 'form'],
        FORBID_ATTR: ['autofocus'],
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
  function resolveImages(el, allowRemote, docId) {
    const api = window.pywebview && window.pywebview.api;
    el.querySelectorAll('img[src]').forEach((img) => {
      const src = img.getAttribute('src');
      if (src.startsWith('data:')) return;
      if (isRemote(src)) {
        if (allowRemote) return;
        img.removeAttribute('src');
        img.dataset.blocked = src;
        img.alt = 'Imagen remota bloqueada. Menu > Cargar imágenes remotas.';
        return;
      }
      if (!api || !api.image_data || !docId) return;
      img.removeAttribute('src');
      api.image_data(docId, src).then((uri) => {
        if (uri) img.src = uri;
        else img.alt = 'No se encontró la imagen: ' + src;
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
  async function renderMermaid(el, theme) {
    const blocks = el.querySelectorAll('.mermaid-block:has(.mermaid-src)');
    if (!blocks.length) return;
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
        block.innerHTML = svg;
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
    unhideCode(el);
    resolveImages(el, o.remoteImages, o.docId);
    addCopyButtons(el);
    markDoneTasks(el);
    renderMath(el);
    return renderMermaid(el, o.theme);
  }

  /** Mostrar texto plano sin interpretar. */
  function renderPlain(text, el) {
    el.innerHTML = '<pre class="plain"><code></code></pre>';
    el.querySelector('code').textContent = text || '';
  }

  return { md, render, renderPlain, buildToc };
})();
