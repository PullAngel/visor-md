/* Estado de la aplicación, pestañas, modos de trabajo, atajos y llamadas a Python. */

(function () {
  // Referencias de la interfaz tomadas una sola vez, con el documento todavía
  // vacío. getElementById devuelve el primero en orden de árbol, y #preview
  // está antes que #menu, #dialog y #ctxmenu: sin esta instantánea, un
  // encabezado llamado "Menú" —markdown-it-anchor le pone id="menu"— o un
  // <div id="dialog"> dentro del documento le roban la referencia a la
  // aplicación, que pasaría a escribir y a escuchar clics en el documento.
  const UI = new Map();
  document.querySelectorAll('[id]').forEach((el) => {
    if (!UI.has(el.id)) UI.set(el.id, el);
  });
  const $ = (id) => UI.get(id) || document.getElementById(id);
  window.__uiRef = $;  // La suite de seguridad comprueba a qué resuelve.
  const editor = $('editor');
  const preview = $('preview');

  // Ajustes de la ventana: no dependen de la pestaña activa.
  const settings = { theme: 'dark', fontSize: 16, toc: false, ready: false };

  // Pestañas abiertas. Solo existe un editor y una vista previa en el DOM: al
  // cambiar de pestaña se vuelca el texto guardado y se vuelve a renderizar.
  const tabs = new Map();
  let activeId = null;

  let api = null;
  const call = (name, ...args) => (api && api[name]
    ? api[name](...args)
    : Promise.reject(new Error('puente no disponible')));

  const active = () => tabs.get(activeId);
  const isMarkdown = (tab) => !['.txt', '.text', '.log'].includes(tab.ext);
  const escapeHtml = (s) => String(s).replace(/[&<>"]/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  /** Cargar texto en el editor dejando el cursor al principio.
      Asignar `value` lo manda al final, y el foco arrastra el scroll con él. */
  function setEditorText(text) {
    editor.value = text;
    editor.setSelectionRange(0, 0);
  }

  /** Volcar el editor en la pestaña activa: su texto vive en el DOM hasta acá. */
  function syncActive() {
    const tab = active();
    if (tab) tab.text = editor.value;
  }

  /** Texto de una pestaña, esté visible o no. */
  function textOf(tab) {
    return tab.id === activeId ? editor.value : tab.text;
  }

  // Interfaz auxiliar

  let toastTimer = null;
  function toast(msg) {
    const el = $('toast');
    el.textContent = msg;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 1900);
  }

  // Los diálogos se encolan: dos abiertos a la vez se pisaban los manejadores
  // y dejaban la primera promesa sin resolver para siempre, lo que congelaba
  // la pestaña que estuviera esperando esa respuesta.
  let dialogQueue = Promise.resolve();

  function dialog(title, bodyHtml, okText, cancelText, onOpen) {
    const show = () => new Promise((resolve) => {
      $('dlg-title').textContent = title;
      $('dlg-body').innerHTML = bodyHtml;
      if (onOpen) onOpen($('dlg-body'));
      $('dlg-ok').textContent = okText || 'Aceptar';
      $('dlg-cancel').hidden = !cancelText;
      if (cancelText) $('dlg-cancel').textContent = cancelText;
      $('dialog').hidden = false;
      $('dlg-ok').focus();
      const done = (v) => {
        $('dialog').hidden = true;
        $('dlg-ok').onclick = null;
        $('dlg-cancel').onclick = null;
        resolve(v);
      };
      $('dlg-ok').onclick = () => done(true);
      $('dlg-cancel').onclick = () => done(false);
    });
    const next = dialogQueue.then(show, show);
    dialogQueue = next.catch(() => {});
    return next;
  }

  async function confirmDiscard(tab) {
    if (!tab.dirty) return true;
    return dialog('Cambios sin guardar',
      `<p>El documento <strong>${escapeHtml(tab.name)}</strong> tiene cambios sin guardar.</p>`,
      'Descartar y continuar', 'Cancelar');
  }

  // Barra de pestañas

  /** Nombre de una pestaña sin archivo: primer encabezado o primera línea. */
  function draftName(tab) {
    const text = (tab.id === activeId ? editor.value : tab.text) || '';
    for (const raw of text.split('\n')) {
      const line = raw.replace(/^#{1,6}\s+/, '').replace(/[*_`>~-]/g, '').trim();
      if (line) return line.length > 24 ? line.slice(0, 24) + '…' : line;
    }
    return 'Sin título';
  }

  const tabLabel = (tab) => (tab.path ? tab.name : draftName(tab));

  function renderTabbar() {
    const box = $('tabs-scroll');
    box.innerHTML = '';
    for (const tab of tabs.values()) {
      const el = document.createElement('div');
      el.className = 'tab' + (tab.id === activeId ? ' active' : '')
        + (tab.path ? '' : ' draft');
      el.dataset.id = tab.id;
      el.setAttribute('role', 'tab');
      el.title = tab.path || (tabLabel(tab) + ' — sin guardar');
      el.innerHTML = `<span class="tab-name"></span>
        <span class="tab-dirty" ${tab.dirty ? '' : 'hidden'}>&#9679;</span>
        <button class="tab-close" title="Cerrar (Ctrl+W)"><svg><use href="#i-close"/></svg></button>`;
      el.querySelector('.tab-name').textContent = tabLabel(tab);
      box.appendChild(el);
    }
    requestAnimationFrame(updateTabOverflow);
  }

  function updateActiveTabChrome(tab) {
    document.title = (tab.dirty ? '* ' : '') + tabLabel(tab) + ' - Visor MD';
    $('btn-plain').hidden = isMarkdown(tab);
    $('menu').querySelector('[data-act="tomd"]').hidden = isMarkdown(tab);
  }

  // Documento activo

  function setDirty(tab, v) {
    tab.dirty = v;
    if (tab.id === activeId) updateActiveTabChrome(tab);
    renderTabbar();
    // El aviso al cerrar lo decide Python, que no puede consultar la página
    // desde el hilo de la interfaz sin bloquearse.
    call('set_dirty', tab.id, v).catch(() => {});
  }

  let renderTimer = null;
  function rerender(immediate) {
    clearTimeout(renderTimer);
    const run = () => {
      const tab = active();
      if (!tab) return;
      if (tab.plain) {
        Render.renderPlain(editor.value, preview);
        $('toc-list').innerHTML = '';
        return;
      }
      Render.render(editor.value, preview, {
        theme: settings.theme,
        // Un solo permiso para las imágenes que no vienen con el documento,
        // sean remotas o locales fuera de su carpeta.
        remoteImages: tab.remoteImages || !settings.blockRemote,
        maxDiagrams: settings.maxDiagrams,
        docId: tab.id,
      }).then(refreshToc);
    };
    if (immediate) run(); else renderTimer = setTimeout(run, 180);
  }

  /** Modo con el que se presenta una pestaña recién cargada.

      Un archivo se abre siempre en lectura, sin recordar el modo anterior.
      Van directo a edición los que no tienen nada que leer: un borrador en
      blanco y los .txt, que son texto plano. */
  function initialMode(tab) {
    return tab.plain || (!tab.path && !tab.text) ? 'edit' : 'read';
  }

  /** Crear el estado local de una pestaña; no la muestra ni la activa. */
  function makeTab(doc) {
    const tab = {
      id: doc.id, path: doc.path || null, name: doc.name, ext: doc.ext || '.md',
      text: doc.text || '', dirty: !!doc.dirty,
      mode: 'read', split: settings.defaultSplit || false,
      plain: false, remoteImages: false, scrollTop: 0,
    };
    tab.plain = !isMarkdown(tab);
    tab.mode = initialMode(tab);
    return tab;
  }

  function addTab(doc, activate) {
    const tab = makeTab(doc);
    tabs.set(tab.id, tab);
    renderTabbar();
    if (activate) switchTab(tab.id);
    return tab;
  }

  function switchTab(id) {
    const tab = tabs.get(id);
    if (!tab || id === activeId) return;
    const prev = active();
    if (prev) {
      prev.text = editor.value;
      prev.scrollTop = prev.mode === 'edit' ? editor.scrollTop : preview.scrollTop;
    }
    activeId = id;
    closeFind();
    setEditorText(tab.text);
    updateActiveTabChrome(tab);
    applyMode(tab, false);
    rerender(true);
    renderTabbar();
    requestAnimationFrame(() => {
      (tab.mode === 'edit' ? editor : preview).scrollTop = tab.scrollTop || 0;
    });
  }

  /** Quitar una pestaña ya cerrada o mudada y dejar otra activa. */
  function dropTabLocally(id) {
    tabs.delete(id);
    if (tabs.size === 0) { call('force_close').catch(() => {}); return; }
    if (id === activeId) {
      const ids = Array.from(tabs.keys());
      activeId = null;
      switchTab(ids[ids.length - 1]);
    } else {
      renderTabbar();
    }
  }

  async function closeTab(id) {
    const tab = tabs.get(id);
    if (!tab) return;
    if (!await confirmDiscard(tab)) return;
    if (!tabs.has(id)) return;  // Se movió a otra ventana mientras preguntábamos.
    call('close_tab', id).catch(() => {});
    dropTabLocally(id);
  }

  async function newTab(focusEditor) {
    const doc = await call('new_tab');
    const tab = addTab(doc, true);
    if (focusEditor !== false) { tab.mode = 'edit'; applyMode(tab, false); editor.focus(); }
    return tab;
  }

  async function openIntoTab(tab, path, fromDocument) {
    const res = await call('open_into', tab.id, path, !!fromDocument);
    if (!res || !res.ok) { toast((res && res.error) || 'No se pudo abrir: ' + path); return null; }
    Object.assign(tab, {
      path: res.path, name: res.name, ext: res.ext || tab.ext, text: res.text || '',
    });
    tab.plain = !isMarkdown(tab);
    // El modo se recalcula acá y no solo al crear la pestaña: abrir un archivo
    // desde el Explorador lo carga sobre una pestaña en blanco, que estaba en
    // edición justamente por estar vacía.
    tab.mode = initialMode(tab);
    tab.dirty = false;
    if (tab.id === activeId) {
      setEditorText(tab.text);
      updateActiveTabChrome(tab);
      applyMode(tab, false);
      rerender(true);
    }
    renderTabbar();
    refreshRecent();
    return tab;
  }

  async function save(tab) {
    tab = tab || active();
    if (!tab) return null;
    if (tab.id === activeId) syncActive();
    if (!tab.path) return saveAs(tab);
    const res = await call('save', tab.id, textOf(tab));
    if (res.ok) { tab.text = textOf(tab); setDirty(tab, false); toast('Guardado'); }
    else if (res.error) toast(res.error);
    return res;
  }

  async function saveAs(tab, ext) {
    tab = tab || active();
    if (!tab) return null;
    if (tab.id === activeId) syncActive();
    const text = textOf(tab);
    const res = await call('save_as', tab.id, text, ext || tab.ext || '.md');
    if (res.cancelled) return res;
    if (!res.ok) { toast(res.error || 'No se pudo guardar'); return res; }
    Object.assign(tab, { path: res.path, name: res.name, ext: res.ext || tab.ext, text });
    setDirty(tab, false);
    if (tab.id === activeId) updateActiveTabChrome(tab);
    renderTabbar();
    refreshRecent();
    toast('Guardado como ' + res.name);
    return res;
  }

  // Modos de trabajo (por pestaña)

  function applyMode(tab, persistPref) {
    const edit = tab.mode === 'edit';
    $('switch').dataset.mode = tab.mode;
    $('mode-read').setAttribute('aria-checked', String(!edit));
    $('mode-edit').setAttribute('aria-checked', String(edit));
    $('fmtbar').hidden = !edit;
    $('btn-split').hidden = !edit;
    $('btn-save').hidden = !edit;
    $('btn-split').setAttribute('aria-pressed', String(tab.split));
    editor.hidden = !edit;
    editor.readOnly = !edit;
    preview.hidden = edit && !tab.split;
    document.body.dataset.split = edit && tab.split ? 'on' : 'off';
    if (!edit) rerender(true);
    if (edit) editor.focus();
    if (persistPref) {
      // El modo no se recuerda a propósito: un archivo se abre siempre en
      // lectura. Solo se guarda la preferencia de vista dividida, que aplica
      // cuando el usuario entra a edición.
      settings.defaultSplit = tab.split;
      persist();
    }
  }

  /** Proporción de scroll de un panel, de 0 a 1. */
  function scrollRatio(el) {
    const max = el.scrollHeight - el.clientHeight;
    return max > 0 ? el.scrollTop / max : 0;
  }

  function applyScrollRatio(el, ratio) {
    const max = el.scrollHeight - el.clientHeight;
    el.scrollTop = max > 0 ? ratio * max : 0;
  }

  function setMode(mode) {
    const tab = active();
    if (!tab) return;
    if (tab.mode === mode) return;
    // Conservar el punto de lectura al cambiar de modo.
    const ratio = scrollRatio(tab.mode === 'edit' ? editor : preview);
    if (tab.mode === 'edit' && mode === 'read') syncActive();
    tab.mode = mode;
    applyMode(tab, true);
    if (mode === 'edit') {
      // El editor se posiciona por número de línea: su altura de scroll aún no
      // es fiable recién mostrado, y el foco lo arrastraría al cursor.
      const lines = editor.value.split('\n');
      const target = Math.round(ratio * lines.length);
      const pos = lines.slice(0, target).join('\n').length;
      editor.setSelectionRange(pos, pos);
      const lh = parseFloat(getComputedStyle(editor).lineHeight) || 24;
      const top = Math.max(0, (target * lh) - editor.clientHeight / 3);
      editor.scrollTop = top;
      requestAnimationFrame(() => { editor.scrollTop = top; });
    } else {
      requestAnimationFrame(() => applyScrollRatio(preview, ratio));
    }
  }

  function setSplit(on) {
    const tab = active();
    if (!tab) return;
    tab.split = on;
    if (tab.mode === 'edit') {
      preview.hidden = !on;
      document.body.dataset.split = on ? 'on' : 'off';
      $('btn-split').setAttribute('aria-pressed', String(on));
      if (on) rerender(true);
    }
    settings.defaultSplit = on;
    persist();
  }

  function setTheme(theme) {
    settings.theme = theme;
    document.documentElement.dataset.theme = theme;
    $('btn-theme').firstElementChild.firstElementChild
      .setAttribute('href', theme === 'dark' ? '#i-moon' : '#i-sun');
    const tab = active();
    if (tab && !tab.plain) rerender(true);
    persist();
  }

  function setFontSize(px) {
    settings.fontSize = Math.min(28, Math.max(11, px));
    document.documentElement.style.setProperty('--doc-size', settings.fontSize + 'px');
    $('font-val').textContent = settings.fontSize + ' px';
    persist();
  }

  function setTypeface(face) {
    settings.face = ['serif', 'mono'].includes(face) ? face : 'sans';
    document.documentElement.dataset.face = settings.face;
    $('menu').querySelectorAll('[data-face]').forEach((b) => {
      b.setAttribute('aria-pressed', String(b.dataset.face === settings.face));
    });
    persist();
  }

  let persistTimer = null;
  function persist() {
    if (!settings.ready) return;
    clearTimeout(persistTimer);
    persistTimer = setTimeout(() => {
      call('save_settings', {
        theme: settings.theme, split: settings.defaultSplit,
        toc: settings.toc, font_size: settings.fontSize, face: settings.face,
        contain_images: settings.containImages, block_remote: settings.blockRemote,
        trusted_dirs: settings.trustedDirs, max_diagrams: settings.maxDiagrams,
      }).catch(() => {});
    }, 400);
  }

  // Índice

  let headings = [];
  function refreshToc() {
    headings = Array.from(Render.buildToc(preview, $('toc-list')));
    $('toc-list').querySelectorAll('a').forEach((a) => {
      a.addEventListener('click', (e) => {
        e.preventDefault();
        const h = document.getElementById(a.dataset.target);
        if (h) h.scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
    spyToc();
  }

  function spyToc() {
    if ($('toc').hidden || !headings.length) return;
    const top = preview.getBoundingClientRect().top + 80;
    let heading = headings[0];
    for (const h of headings) {
      if (h.getBoundingClientRect().top <= top) heading = h; else break;
    }
    $('toc-list').querySelectorAll('a').forEach((a) => {
      a.classList.toggle('active', a.dataset.target === heading.id);
    });
  }

  function setToc(on) {
    settings.toc = on;
    $('toc').hidden = !on;
    $('btn-toc').setAttribute('aria-pressed', String(on));
    if (on) spyToc();
    persist();
  }

  // Buscar y reemplazar

  const find = { matches: [], index: 0, query: '' };

  function textNodes(root) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => (n.nodeValue.trim() && n.parentElement.offsetParent !== null
        ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT),
    });
    const out = [];
    let n;
    while ((n = walker.nextNode())) out.push(n);
    return out;
  }

  function clearHighlights() {
    if (window.CSS && CSS.highlights) {
      CSS.highlights.delete('find');
      CSS.highlights.delete('find-current');
    }
  }

  function runFind(query) {
    find.query = query;
    find.matches = [];
    find.index = 0;
    clearHighlights();
    if (!query) { $('find-count').textContent = '0/0'; return; }
    const tab = active();
    const q = query.toLowerCase();

    if (tab && tab.mode === 'edit') {
      const hay = editor.value.toLowerCase();
      let i = hay.indexOf(q);
      while (i !== -1) { find.matches.push(i); i = hay.indexOf(q, i + q.length); }
    } else {
      for (const node of textNodes(preview)) {
        const hay = node.nodeValue.toLowerCase();
        let i = hay.indexOf(q);
        while (i !== -1) {
          const r = document.createRange();
          r.setStart(node, i);
          r.setEnd(node, i + q.length);
          find.matches.push(r);
          i = hay.indexOf(q, i + q.length);
        }
      }
      if (window.CSS && CSS.highlights && find.matches.length) {
        CSS.highlights.set('find', new Highlight(...find.matches));
      }
    }
    updateFindUi();
    if (find.matches.length) gotoMatch(0);
  }

  function updateFindUi() {
    $('find-count').textContent = find.matches.length
      ? `${find.index + 1}/${find.matches.length}` : '0/0';
  }

  function gotoMatch(i) {
    if (!find.matches.length) return;
    find.index = (i + find.matches.length) % find.matches.length;
    const m = find.matches[find.index];
    const tab = active();
    if (tab && tab.mode === 'edit') {
      editor.focus();
      editor.setSelectionRange(m, m + find.query.length);
      const line = editor.value.slice(0, m).split('\n').length;
      const lh = parseFloat(getComputedStyle(editor).lineHeight) || 24;
      editor.scrollTop = Math.max(0, (line - 1) * lh - editor.clientHeight / 2);
    } else {
      if (window.CSS && CSS.highlights) CSS.highlights.set('find-current', new Highlight(m));
      const rect = m.getBoundingClientRect();
      const box = preview.getBoundingClientRect();
      if (rect.top < box.top + 40 || rect.bottom > box.bottom - 40) {
        preview.scrollTop += rect.top - box.top - preview.clientHeight / 2;
      }
    }
    updateFindUi();
  }

  function openFind(replace) {
    $('findbar').hidden = false;
    const tab = active();
    const showReplace = !!replace && tab && tab.mode === 'edit';
    ['replace-input', 'replace-one', 'replace-all'].forEach((id) => {
      $(id).hidden = !showReplace;
    });
    $('find-input').focus();
    $('find-input').select();
    if ($('find-input').value) runFind($('find-input').value);
  }

  function closeFind() {
    $('findbar').hidden = true;
    clearHighlights();
    find.matches = [];
  }

  function replaceOne() {
    const tab = active();
    if (!tab || tab.mode !== 'edit' || !find.matches.length) return;
    const pos = find.matches[find.index];
    Editor.replaceRange(pos, pos + find.query.length, $('replace-input').value);
    onInput();
    runFind(find.query);
  }

  function replaceAll() {
    const tab = active();
    if (!tab || tab.mode !== 'edit' || !find.matches.length) return;
    const n = find.matches.length;
    const re = new RegExp(find.query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi');
    editor.focus();
    editor.setSelectionRange(0, editor.value.length);
    document.execCommand('insertText', false, editor.value.replace(re, $('replace-input').value));
    onInput();
    runFind(find.query);
    toast(`${n} reemplazo${n === 1 ? '' : 's'}`);
  }

  // Eventos del editor

  let labelTimer = null;
  function onInput() {
    const tab = active();
    if (!tab) return;
    tab.text = editor.value;
    if (!tab.dirty) setDirty(tab, true);
    // Una pestaña sin archivo se nombra por su contenido: hay que refrescarla
    // mientras se escribe, no solo al ensuciarse.
    if (!tab.path) {
      clearTimeout(labelTimer);
      labelTimer = setTimeout(() => { renderTabbar(); updateActiveTabChrome(tab); }, 400);
    }
    if (tab.mode === 'edit' && (tab.split || tab.plain)) rerender(false);
  }

  editor.addEventListener('input', () => {
    if (splitActivo()) setDriver(editor);
    onInput();
  });
  Editor.init(editor, () => {});

  let syncing = false;
  function syncScroll(from, to) {
    if (syncing) return;
    syncing = true;
    const max = from.scrollHeight - from.clientHeight;
    const ratio = max > 0 ? from.scrollTop / max : 0;
    to.scrollTop = ratio * (to.scrollHeight - to.clientHeight);
    requestAnimationFrame(() => { syncing = false; });
  }

  // Cuál de los dos paneles manda el scroll en vista dividida. Al escribir,
  // volver a renderizar reemplaza el HTML de la vista previa y eso dispara su
  // evento de scroll con una posición que ya no corresponde; sin este mando,
  // ese eco arrastraba el editor y el texto que se estaba escribiendo se iba
  // de pantalla.
  let driver = null;
  let driverTimer = null;
  function setDriver(el) {
    driver = el;
    clearTimeout(driverTimer);
    driverTimer = setTimeout(() => { driver = null; }, 260);
  }

  const splitActivo = () => {
    const tab = active();
    return !!(tab && tab.split && tab.mode === 'edit');
  };

  editor.addEventListener('scroll', () => {
    if (!splitActivo()) return;
    if (driver && driver !== editor) return;
    setDriver(editor);
    syncScroll(editor, preview);
  });
  preview.addEventListener('scroll', () => {
    if (!splitActivo()) { spyToc(); return; }
    if (driver && driver !== preview) return;
    setDriver(preview);
    syncScroll(preview, editor);
  });

  $('mode-read').addEventListener('click', () => setMode('read'));
  $('mode-edit').addEventListener('click', () => setMode('edit'));
  $('btn-split').addEventListener('click', () => setSplit(!active().split));
  $('btn-toc').addEventListener('click', () => setToc(!settings.toc));
  $('btn-find').addEventListener('click', () => openFind(false));
  $('btn-save').addEventListener('click', () => save());
  $('btn-theme').addEventListener('click', () => setTheme(settings.theme === 'dark' ? 'light' : 'dark'));
  $('btn-plain').addEventListener('click', () => {
    const tab = active();
    if (!tab) return;
    tab.plain = !tab.plain;
    $('btn-plain').textContent = tab.plain
      ? 'Interpretar como Markdown' : 'Ver como texto plano';
    if (tab.mode === 'edit' && !tab.split) setSplit(true);
    rerender(true);
  });

  $('fmtbar').addEventListener('click', (e) => {
    const btn = e.target.closest('button[data-fmt]');
    if (!btn) return;
    Editor.apply(btn.dataset.fmt);
    onInput();
  });

  $('find-input').addEventListener('input', (e) => runFind(e.target.value));
  $('find-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); gotoMatch(find.index + (e.shiftKey ? -1 : 1)); }
    if (e.key === 'Escape') closeFind();
  });
  $('find-next').addEventListener('click', () => gotoMatch(find.index + 1));
  $('find-prev').addEventListener('click', () => gotoMatch(find.index - 1));
  $('find-close').addEventListener('click', closeFind);
  $('replace-one').addEventListener('click', replaceOne);
  $('replace-all').addEventListener('click', replaceAll);

  // Arrastre de pestañas con eventos de puntero, no con drag-and-drop de
  // HTML5 (que no permite soltar limpiamente fuera de la ventana ni sobre
  // otra ventana de la misma app).

  let drag = null;

  function tabbarBottom() {
    return $('tabbar').getBoundingClientRect().bottom;
  }

  function pointerInBar(e) {
    return e.clientY <= tabbarBottom() + 30 && e.clientY >= -20
      && e.clientX >= 0 && e.clientX <= window.innerWidth;
  }

  function moveGhost(e) {
    drag.ghost.style.transform = `translate(${e.clientX + 10}px, ${e.clientY + 12}px)`;
  }

  function markDropTarget(e) {
    document.querySelectorAll('.tab.drop-before, .tab.drop-after')
      .forEach((el) => el.classList.remove('drop-before', 'drop-after'));
    if (!pointerInBar(e)) return null;
    const over = document.elementFromPoint(e.clientX, Math.min(e.clientY, tabbarBottom() - 4));
    const tabEl = over && over.closest ? over.closest('.tab') : null;
    if (!tabEl || tabEl.dataset.id === drag.id) return null;
    const rect = tabEl.getBoundingClientRect();
    const before = e.clientX < rect.left + rect.width / 2;
    tabEl.classList.add(before ? 'drop-before' : 'drop-after');
    return { id: tabEl.dataset.id, before };
  }

  function reorder(dragId, targetId, before) {
    const entries = Array.from(tabs.entries());
    const fromIdx = entries.findIndex(([id]) => id === dragId);
    const [moved] = entries.splice(fromIdx, 1);
    let toIdx = entries.findIndex(([id]) => id === targetId);
    if (!before) toIdx += 1;
    entries.splice(toIdx, 0, moved);
    tabs.clear();
    entries.forEach(([id, t]) => tabs.set(id, t));
    renderTabbar();
  }

  function endDrag() {
    if (!drag) return;
    if (drag.ghost) drag.ghost.remove();
    document.querySelectorAll('.tab.dragging, .tab.drop-before, .tab.drop-after')
      .forEach((el) => el.classList.remove('dragging', 'drop-before', 'drop-after'));
    drag = null;
  }

  $('tabs-scroll').addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || e.target.closest('.tab-close')) return;
    const tabEl = e.target.closest('.tab');
    if (!tabEl) return;
    switchTab(tabEl.dataset.id);
    drag = { id: tabEl.dataset.id, startX: e.clientX, startY: e.clientY,
             started: false, drop: null, pointerId: e.pointerId };
    // Mantiene el arrastre activo aunque el puntero salga de la ventana.
    try { $('tabs-scroll').setPointerCapture(e.pointerId); } catch (err) { /* sin captura */ }
  });

  $('tabs-scroll').addEventListener('pointermove', (e) => {
    if (!drag) return;
    if (!drag.started) {
      if (Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) < 6) return;
      drag.started = true;
      const tab = tabs.get(drag.id);
      const ghost = document.createElement('div');
      ghost.className = 'tab-ghost';
      ghost.textContent = tab ? tab.name : '';
      document.body.appendChild(ghost);
      drag.ghost = ghost;
      const el = $('tabs-scroll').querySelector(`.tab[data-id="${drag.id}"]`);
      if (el) el.classList.add('dragging');
    }
    moveGhost(e);
    drag.drop = markDropTarget(e);
    drag.ghost.classList.toggle('detach', !pointerInBar(e));
  });

  $('tabs-scroll').addEventListener('pointerup', async (e) => {
    if (!drag) return;
    const { id, started, drop } = drag;
    const inBar = pointerInBar(e);
    endDrag();
    if (!started) return;          // Fue un clic: la pestaña ya quedó activa.
    if (inBar) {
      if (drop) reorder(id, drop.id, drop.before);
      return;
    }
    const tab = tabs.get(id);
    if (!tab) return;
    syncActive();
    // Python decide el destino según lo que haya bajo el puntero. Solo se
    // permite crear una ventana nueva si queda alguna pestaña acá.
    const res = await call('drop_tab', id, textOf(tab), tabs.size > 1).catch(() => null);
    if (res && res.ok) dropTabLocally(id);
  });

  $('tabs-scroll').addEventListener('pointercancel', endDrag);

  $('tabs-scroll').addEventListener('click', (e) => {
    const close = e.target.closest('.tab-close');
    if (close) closeTab(close.closest('.tab').dataset.id);
  });

  $('tabs-scroll').addEventListener('auxclick', (e) => {
    const tabEl = e.target.closest('.tab');
    if (tabEl && e.button === 1) closeTab(tabEl.dataset.id);
  });

  $('btn-newtab').addEventListener('click', () => newTab());

  // La barra de pestañas se desplaza con la rueda cuando hay muchas abiertas.
  $('tabs-scroll').addEventListener('wheel', (e) => {
    if (e.deltaY === 0) return;
    e.preventDefault();
    $('tabs-scroll').scrollLeft += e.deltaY;
  }, { passive: false });

  // Barra de título propia

  $('win-min').addEventListener('click', () => call('minimize_window').catch(() => {}));
  $('win-max').addEventListener('click', () => toggleMaximize());
  $('win-close').addEventListener('click', () => call('close_window').catch(() => {}));

  async function toggleMaximize() {
    const max = await call('toggle_maximize').catch(() => null);
    if (max === null) return;
    marcarSinBordes(max);
  }

  async function toggleFullscreen() {
    const on = await call('toggle_fullscreen').catch(() => null);
    if (on === null) return;
    marcarSinBordes(on);
  }

  // El borde de un pixel del cuerpo solo tiene sentido con la ventana suelta:
  // pegada a los lados de la pantalla se vería como una línea de más.
  function marcarSinBordes(activo) {
    document.body.classList.toggle('maximizada', activo);
    $('win-max').firstElementChild.firstElementChild
      .setAttribute('href', activo ? '#i-restore' : '#i-max');
  }

  // Arrastrar la ventana desde el hueco libre de la barra.
  let winDrag = null;
  $('drag-zone').addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    winDrag = { x: e.screenX, y: e.screenY };
    $('drag-zone').setPointerCapture(e.pointerId);
  });
  $('drag-zone').addEventListener('pointermove', (e) => {
    if (!winDrag) return;
    const dx = e.screenX - winDrag.x;
    const dy = e.screenY - winDrag.y;
    if (!dx && !dy) return;
    winDrag = { x: e.screenX, y: e.screenY };
    call('move_window', dx, dy).catch(() => {});
  });
  $('drag-zone').addEventListener('pointerup', () => { winDrag = null; });
  $('drag-zone').addEventListener('dblclick', () => toggleMaximize());

  // Lista de todas las pestañas

  function renderTabList() {
    const box = $('tablist');
    box.innerHTML = '';
    for (const tab of tabs.values()) {
      const b = document.createElement('button');
      b.className = tab.id === activeId ? 'active' : '';
      b.title = tab.path || '';
      b.innerHTML = '<span class="tl-name"></span>'
        + (tab.dirty ? '<span class="tl-dirty">&#9679;</span>' : '');
      b.querySelector('.tl-name').textContent = tabLabel(tab);
      b.addEventListener('click', () => {
        box.hidden = true;
        switchTab(tab.id);
      });
      box.appendChild(b);
    }
  }

  $('btn-tablist').addEventListener('click', (e) => {
    e.stopPropagation();
    const box = $('tablist');
    if (box.hidden) { renderTabList(); box.hidden = false; } else { box.hidden = true; }
  });

  /** El selector de pestañas solo aparece cuando dejan de entrar en la barra. */
  function updateTabOverflow() {
    const strip = $('tabs-scroll');
    $('btn-tablist').hidden = strip.scrollWidth <= strip.clientWidth + 4;
  }

  // Menú

  function toggleMenu(show) {
    $('menu').hidden = show === undefined ? !$('menu').hidden : !show;
    if (!$('menu').hidden) refreshRecent();
  }
  $('btn-menu').addEventListener('click', (e) => { e.stopPropagation(); toggleMenu(); });
  document.addEventListener('click', (e) => {
    if (!$('menu').hidden && !e.target.closest('#menu')) toggleMenu(false);
  });

  async function refreshRecent() {
    if (!api) return;
    const list = await call('recent').catch(() => []);
    const openPaths = new Set(Array.from(tabs.values()).map((t) => t.path));
    const box = $('recent-list');
    box.innerHTML = '';
    list.filter((r) => !openPaths.has(r.path)).slice(0, 5).forEach((r) => {
      const b = document.createElement('button');
      b.textContent = r.name;
      b.title = r.path;
      b.addEventListener('click', async () => {
        toggleMenu(false);
        const tab = await newTab(false);
        openIntoTab(tab, r.path);
      });
      box.appendChild(b);
    });
  }

  /* Configuración avanzada: aflojar las restricciones de acceso a recursos
     para trabajar con documentos propios. No expone la sanitización, la CSP
     ni los protocolos permitidos: esos separan mostrar un documento de
     ejecutar lo que trae dentro, y no hay trabajo legítimo que los necesite
     apagados. Ver docs/frontera-de-seguridad.md. */
  async function advancedDialog() {
    const trusted = (settings.trustedDirs || []).slice();
    let campos = null;

    const pintarCarpetas = (body) => {
      const box = body.querySelector('#adv-dirs');
      box.innerHTML = '';
      if (!trusted.length) {
        const p = document.createElement('p');
        p.className = 'adv-empty';
        p.textContent = 'Ninguna. Los documentos se tratan todos igual.';
        box.appendChild(p);
        return;
      }
      trusted.forEach((dir, i) => {
        const row = document.createElement('div');
        row.className = 'adv-dir';
        const nombre = document.createElement('span');
        nombre.textContent = dir;
        nombre.title = dir;
        const quitar = document.createElement('button');
        quitar.type = 'button';
        quitar.textContent = 'Quitar';
        quitar.addEventListener('click', () => {
          trusted.splice(i, 1);
          pintarCarpetas(body);
        });
        row.append(nombre, quitar);
        box.appendChild(row);
      });
    };

    const ok = await dialog('Configuración avanzada',
      `<p class="adv-intro">Un documento Markdown puede venir de cualquier parte, así que
         de entrada se le da el mínimo acceso. Acá se afloja para trabajar con documentos propios.</p>
       <label class="adv-check"><input type="checkbox" id="adv-contain">
         Cargar solo las imágenes que estén en la carpeta del documento o por debajo</label>
       <label class="adv-check"><input type="checkbox" id="adv-remote">
         Bloquear las imágenes remotas hasta pedirlas</label>
       <label class="adv-num">Máximo de diagramas por documento
         <input type="number" id="adv-diagrams" min="1" max="500" step="1"></label>
       <div class="menu-label">Carpetas de confianza</div>
       <p class="adv-intro">Los documentos que estén dentro de estas carpetas cargan sus
         imágenes sin restricción, sin cambiar el resto de los ajustes.</p>
       <div id="adv-dirs"></div>
       <button type="button" id="adv-add" class="adv-add">Agregar carpeta…</button>`,
      'Guardar', 'Cancelar',
      (body) => {
        // Los controles se guardan acá: si otro diálogo se encola detrás,
        // reemplaza el contenido de #dlg-body y estas referencias siguen
        // conservando lo que el usuario eligió.
        campos = {
          contain: body.querySelector('#adv-contain'),
          remote: body.querySelector('#adv-remote'),
          diagrams: body.querySelector('#adv-diagrams'),
        };
        campos.contain.checked = settings.containImages;
        campos.remote.checked = settings.blockRemote;
        campos.diagrams.value = settings.maxDiagrams;
        pintarCarpetas(body);
        body.querySelector('#adv-add').addEventListener('click', async () => {
          const dir = await call('pick_folder').catch(() => null);
          if (dir && !trusted.includes(dir)) trusted.push(dir);
          pintarCarpetas(body);
        });
      });
    if (!ok || !campos) return;

    settings.containImages = campos.contain.checked;
    settings.blockRemote = campos.remote.checked;
    settings.maxDiagrams = Math.min(500, Math.max(1,
      parseInt(campos.diagrams.value, 10) || 50));
    settings.trustedDirs = trusted;
    persist();
    rerender(true);
    toast('Configuración guardada');
  }

  const MENU_ACTIONS = {
    newtab: () => newTab(),
    newwindow: () => call('new_window').catch(() => {}),
    open: async () => {
      const paths = await call('open_dialog').catch(() => []);
      let last = null;
      for (const p of paths) {
        const tab = await newTab(false);
        last = await openIntoTab(tab, p);
      }
      if (last) switchTab(last.id);
    },
    closetab: () => { const t = active(); if (t) closeTab(t.id); },
    save: () => save(),
    saveas: () => saveAs(active()),
    tomd: async () => {
      const res = await saveAs(active(), '.md');
      if (res && res.ok) { active().plain = false; rerender(true); setMode('read'); }
    },
    copyall: async () => {
      await navigator.clipboard.writeText(editor.value);
      toast('Markdown copiado');
    },
    images: () => {
      const tab = active();
      if (!tab) return;
      tab.remoteImages = !tab.remoteImages;
      rerender(true);
      toast(tab.remoteImages ? 'Imágenes bloqueadas cargadas' : 'Imágenes bloqueadas otra vez');
    },
    advanced: () => advancedDialog(),
    export: async () => {
      const tab = active();
      if (!tab) return;
      if (tab.plain) rerender(true);
      const res = await call('export_html', tab.id, preview.innerHTML, tab.name);
      if (res.ok) toast('Exportado a ' + res.path.split('\\').pop());
      else if (res.error) toast(res.error);
    },
    print: () => {
      const tab = active();
      if (tab && tab.mode === 'edit') setMode('read');
      setTimeout(() => window.print(), 120);
    },
    reveal: () => { const t = active(); if (t) call('reveal', t.id).catch(() => {}); },
    fullscreen: toggleFullscreen,
    'font+': () => setFontSize(settings.fontSize + 1),
    'font-': () => setFontSize(settings.fontSize - 1),
    defaults: () => call('open_default_apps').catch(() => {}),
    install: installFlow,
    about: () => dialog('Visor MD',
      `<p>Visor y editor de Markdown para Windows.</p>
       <p>Atajos: <strong>Ctrl+T</strong> pestaña nueva, <strong>Ctrl+Shift+N</strong> ventana nueva,
       <strong>Ctrl+W</strong> cerrar pestaña, <strong>Ctrl+R</strong> lectura,
       <strong>Ctrl+E</strong> edición, <strong>Ctrl+\\</strong> vista dividida,
       <strong>Ctrl+S</strong> guardar, <strong>Ctrl+F</strong> buscar,
       <strong>Ctrl+H</strong> reemplazar, <strong>Ctrl+D</strong> tema,
       <strong>Ctrl+Shift+O</strong> índice.</p>
       <p>Las pestañas se arrastran para reordenarlas, se sueltan sobre otra
       ventana para moverlas, o fuera de la barra para abrirlas aparte.</p>`, 'Cerrar'),
  };

  $('menu').addEventListener('click', (e) => {
    const face = e.target.closest('button[data-face]');
    if (face) { setTypeface(face.dataset.face); return; }
    const btn = e.target.closest('button[data-act]');
    if (!btn) return;
    const act = btn.dataset.act;
    if (!act.startsWith('font')) toggleMenu(false);
    (MENU_ACTIONS[act] || (() => {}))();
  });

  async function installFlow() {
    const status = await call('shell_status').catch(() => null);
    if (!status) return;
    if (!status.frozen) {
      dialog('Instalar', '<p>La instalación solo funciona sobre el ejecutable compilado '
        + '(<strong>VisorMD.exe</strong>).</p>', 'Entendido');
      return;
    }
    const ok = await dialog('Instalar Visor MD',
      `<p>Se copiará la aplicación a la carpeta del usuario y se registrará para abrir
       archivos <strong>.md</strong>, <strong>.markdown</strong> y <strong>.txt</strong>.</p>
       <p>No requiere permisos de administrador y se desinstala desde
       Configuración, Aplicaciones.</p>`, 'Instalar', 'Cancelar');
    if (!ok) return;
    const res = await call('install');
    if (!res.ok) { toast(res.error || 'No se pudo instalar'); return; }
    const go = await dialog('Instalación completada',
      `<p>Windows no permite que un programa se establezca solo como predeterminado.
       El último paso es manual:</p>
       <ol>
         <li>Clic derecho sobre cualquier archivo <strong>.md</strong></li>
         <li><strong>Abrir con</strong>, <strong>Elegir otra aplicación</strong></li>
         <li>Seleccionar <strong>Visor MD</strong> y marcar
             <strong>Usar siempre esta aplicación</strong></li>
       </ol>`, 'Abrir configuración de Windows', 'Despues');
    if (go) call('open_default_apps').catch(() => {});
  }

  // Menú del clic derecho
  //
  // WebView2 no trae menú nativo fuera de modo depuración, así que se arma uno
  // propio con lo que corresponde a lo que hay debajo del puntero.

  function closeCtx() { $('ctxmenu').hidden = true; }

  function showCtx(x, y, items) {
    const box = $('ctxmenu');
    box.innerHTML = '';
    let last = null;
    for (const it of items) {
      if (!it) continue;
      if (it === '-') {
        if (last === '-' || !box.childElementCount) continue;
        box.appendChild(document.createElement('hr'));
      } else {
        const b = document.createElement('button');
        b.innerHTML = `<span></span>${it.key ? `<kbd>${it.key}</kbd>` : ''}`;
        b.firstElementChild.textContent = it.label;
        b.addEventListener('click', () => { closeCtx(); it.run(); });
        box.appendChild(b);
      }
      last = it === '-' ? '-' : null;
    }
    if (!box.childElementCount) return;
    box.hidden = false;
    // Reubicar si se sale por el borde derecho o inferior.
    const r = box.getBoundingClientRect();
    box.style.left = Math.min(x, window.innerWidth - r.width - 8) + 'px';
    box.style.top = Math.min(y, window.innerHeight - r.height - 8) + 'px';
  }

  const selectedText = () => String(window.getSelection() || '').trim();

  function ctxForTab(tabEl) {
    const id = tabEl.dataset.id;
    const tab = tabs.get(id);
    const ids = Array.from(tabs.keys());
    const idx = ids.indexOf(id);
    return [
      { label: 'Cerrar pestaña', key: 'Ctrl+W', run: () => closeTab(id) },
      { label: 'Cerrar las demás', run: async () => {
        for (const other of ids.filter((x) => x !== id)) await closeTab(other);
      } },
      { label: 'Cerrar las de la derecha', run: async () => {
        for (const other of ids.slice(idx + 1)) await closeTab(other);
      } },
      '-',
      { label: 'Mover a una ventana nueva', run: async () => {
        if (tabs.size < 2) return;
        syncActive();
        const res = await call('move_tab_to_new_window', id, textOf(tab)).catch(() => null);
        if (res && res.ok) dropTabLocally(id);
      } },
      tab && tab.path ? '-' : null,
      tab && tab.path
        ? { label: 'Copiar ruta', run: () => navigator.clipboard.writeText(tab.path) }
        : null,
      tab && tab.path
        ? { label: 'Abrir carpeta contenedora', run: () => call('reveal', id).catch(() => {}) }
        : null,
    ];
  }

  function ctxForEditor() {
    const sel = editor.selectionStart !== editor.selectionEnd;
    const fmt = (kind) => () => { Editor.apply(kind); onInput(); };
    return [
      { label: 'Cortar', key: 'Ctrl+X', run: () => {
        if (!sel) return;
        navigator.clipboard.writeText(editor.value.slice(editor.selectionStart, editor.selectionEnd));
        document.execCommand('insertText', false, '');
        onInput();
      } },
      { label: 'Copiar', key: 'Ctrl+C', run: () => {
        navigator.clipboard.writeText(editor.value.slice(editor.selectionStart, editor.selectionEnd));
      } },
      { label: 'Pegar', key: 'Ctrl+V', run: async () => {
        try {
          const text = await navigator.clipboard.readText();
          editor.focus();
          document.execCommand('insertText', false, text);
          onInput();
        } catch (e) { toast('Usá Ctrl+V para pegar'); }
      } },
      '-',
      { label: 'Negrita', key: 'Ctrl+B', run: fmt('bold') },
      { label: 'Cursiva', key: 'Ctrl+I', run: fmt('italic') },
      { label: 'Código', key: 'Ctrl+`', run: fmt('code') },
      { label: 'Enlace', key: 'Ctrl+K', run: fmt('link') },
      '-',
      { label: 'Seleccionar todo', key: 'Ctrl+A', run: () => editor.select() },
    ];
  }

  function ctxForPreview(target) {
    const link = target.closest('a[href]');
    const href = link ? link.getAttribute('href') : '';
    const block = target.closest('.codeblock');
    const img = target.closest('img');
    const sel = selectedText();
    return [
      sel ? { label: 'Copiar', key: 'Ctrl+C',
              run: () => navigator.clipboard.writeText(sel) } : null,
      sel ? { label: `Buscar "${sel.length > 18 ? sel.slice(0, 18) + '…' : sel}"`,
              run: () => { $('find-input').value = sel; openFind(false); runFind(sel); } } : null,
      link && /^(https?:|mailto:)/i.test(href)
        ? { label: 'Abrir en el navegador', run: () => call('open_external', href).catch(() => {}) }
        : null,
      link ? { label: 'Copiar dirección del enlace',
               run: () => navigator.clipboard.writeText(href) } : null,
      block ? { label: 'Copiar bloque de código', run: () => {
        navigator.clipboard.writeText(block.querySelector('code').textContent);
        toast('Bloque copiado');
      } } : null,
      img && img.dataset.blocked
        ? { label: 'Cargar imágenes remotas', run: () => MENU_ACTIONS.images() }
        : null,
      '-',
      { label: 'Editar este documento', key: 'Ctrl+E', run: () => setMode('edit') },
      { label: 'Copiar todo el Markdown', run: () => MENU_ACTIONS.copyall() },
    ];
  }

  document.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    const tabEl = e.target.closest('.tab');
    if (tabEl) { showCtx(e.clientX, e.clientY, ctxForTab(tabEl)); return; }
    if (e.target === editor) { showCtx(e.clientX, e.clientY, ctxForEditor()); return; }
    if (e.target.closest('#preview')) {
      showCtx(e.clientX, e.clientY, ctxForPreview(e.target));
      return;
    }
    showCtx(e.clientX, e.clientY, [
      { label: 'Nueva pestaña', key: 'Ctrl+T', run: () => newTab() },
      { label: 'Abrir…', key: 'Ctrl+O', run: () => MENU_ACTIONS.open() },
      { label: 'Nueva ventana', key: 'Ctrl+Shift+N',
        run: () => call('new_window').catch(() => {}) },
    ]);
  });

  document.addEventListener('pointerdown', (e) => {
    if (!$('ctxmenu').hidden && !e.target.closest('#ctxmenu')) closeCtx();
    if (!$('tablist').hidden && !e.target.closest('#tablist, #btn-tablist')) {
      $('tablist').hidden = true;
    }
  });
  window.addEventListener('blur', closeCtx);

  // Enlaces del documento. Solo se abren http, https y mailto; el resto queda
  // inerte. auxclick cubre el clic central, que no dispara el evento click y
  // acabaria en el manejador de ventanas nuevas de pywebview.

  preview.addEventListener('auxclick', (e) => e.preventDefault());

  preview.addEventListener('click', async (e) => {
    const a = e.target.closest('a');
    if (!a) return;
    const href = a.getAttribute('href') || '';
    if (href.startsWith('#')) return;
    e.preventDefault();
    if (/^(https?:|mailto:)/i.test(href)) {
      call('open_external', href).catch(() => {});
      return;
    }
    if (/\.(md|markdown|mdown|mkd|txt)$/i.test(href)) {
      const tab = active();
      if (!tab) return;
      if (!await confirmDiscard(tab)) return;
      // La ruta la propone el documento: Python la filtra en consecuencia.
      await openIntoTab(tab, href, true);
    }
  });

  // Atajos

  document.addEventListener('keydown', (e) => {
    const ctrl = e.ctrlKey || e.metaKey;
    if (e.key === 'Escape') {
      if (!$('ctxmenu').hidden) closeCtx();
      else if (!$('tablist').hidden) $('tablist').hidden = true;
      else if (!$('menu').hidden) toggleMenu(false);
      else if (!$('findbar').hidden) closeFind();
      else if (!$('dialog').hidden) $('dlg-cancel').click();
      return;
    }
    if (e.key === 'F11') { e.preventDefault(); toggleFullscreen(); return; }
    if (!ctrl) return;
    const k = e.key.toLowerCase();
    const tab = active();
    const global = {
      t: () => newTab(),
      w: () => { if (tab) closeTab(tab.id); },
      n: () => { if (e.shiftKey) call('new_window').catch(() => {}); },
      s: () => (e.shiftKey ? saveAs(tab) : save(tab)),
      o: () => (e.shiftKey ? setToc(!settings.toc) : MENU_ACTIONS.open()),
      f: () => openFind(false),
      h: () => { if (tab && tab.mode === 'edit') openFind(true); },
      e: () => setMode('edit'),
      r: () => setMode('read'),
      d: () => setTheme(settings.theme === 'dark' ? 'light' : 'dark'),
      '\\': () => { if (tab && tab.mode === 'edit') setSplit(!tab.split); },
      p: () => MENU_ACTIONS.print(),
      '+': () => setFontSize(settings.fontSize + 1),
      '=': () => setFontSize(settings.fontSize + 1),
      '-': () => setFontSize(settings.fontSize - 1),
      tab: () => {
        const ids = Array.from(tabs.keys());
        const idx = ids.indexOf(activeId);
        const next = e.shiftKey ? (idx - 1 + ids.length) % ids.length : (idx + 1) % ids.length;
        switchTab(ids[next]);
      },
    };
    const format = { b: 'bold', i: 'italic', k: 'link', '`': 'code', 1: 'h1', 2: 'h2', 3: 'h3' };
    const formatShift = { x: 'strike', c: 'fence', t: 'task', 7: 'ol', 8: 'ul', '.': 'quote' };

    if (tab && tab.mode === 'edit' && document.activeElement === editor) {
      const kind = e.shiftKey ? formatShift[k] : format[k];
      if (kind && k !== 't') { e.preventDefault(); Editor.apply(kind); onInput(); return; }
    }
    const key = e.key === 'Tab' ? 'tab' : k;
    if (global[key]) { e.preventDefault(); global[key](); }
  });

  // Cambios externos del archivo

  let checkingDisk = false;
  window.addEventListener('focus', async () => {
    call('focus_window').catch(() => {});
    const tab = active();
    if (!api || !tab || !tab.path || checkingDisk) return;
    checkingDisk = true;
    try {
      const changed = await call('changed_on_disk', tab.id).catch(() => false);
      if (!changed || !tabs.has(tab.id)) return;
      const msg = tab.dirty
        ? `<p><strong>${escapeHtml(tab.name)}</strong> cambió fuera de Visor MD y hay cambios sin guardar.</p>
           <p>Al recargar se pierden los cambios locales.</p>`
        : `<p><strong>${escapeHtml(tab.name)}</strong> cambió fuera de Visor MD.</p>`;
      if (await dialog('El archivo cambió en el disco', msg, 'Recargar', 'Mantener lo actual')) {
        if (tabs.has(tab.id)) await openIntoTab(tab, tab.path);
      }
    } finally {
      checkingDisk = false;
    }
  });

  // Llamadas que llegan desde Python

  /** Otra instancia abrió un archivo: se agrega como pestaña y se enfoca. */
  window.__openExternalTab = async (path) => {
    if (!path) return;
    const tab = await newTab(false);
    await openIntoTab(tab, path);
    switchTab(tab.id);
  };

  /** Una pestaña arrastrada desde otra ventana aterriza acá. */
  window.__acceptTab = (doc) => {
    if (!doc || !doc.id) return;
    addTab(doc, true);
    if (doc.dirty) call('set_dirty', doc.id, true).catch(() => {});
    window.focus();
  };

  /** Abrir una pestaña vacía. Lo usa la prueba automática. */
  window.__newTabForTest = () => newTab(false);

  /** Guardar una pestaña por nombre. Lo usa la prueba automática. */
  window.__saveByName = (name) => {
    for (const tab of tabs.values()) {
      if (tab.name === name) return save(tab);
    }
    return null;
  };

  /** Aviso de cierre con estilo propio, en vez del cuadro gris de Windows. */
  window.__confirmClose = async (names) => {
    const list = (names || []).map((n) => `<li>${escapeHtml(n)}</li>`).join('');
    const ok = await dialog('Cambios sin guardar',
      `<p>Estas pestañas tienen cambios sin guardar:</p><ul>${list}</ul>
       <p>Si cerrás la ventana, se pierden.</p>`,
      'Cerrar sin guardar', 'Volver');
    if (ok) call('force_close').catch(() => {});
  };

  // Arranque

  async function boot() {
    api = window.pywebview.api;
    const info = await api.startup();
    const s = info.settings || {};
    settings.ready = false;
    settings.defaultSplit = !!s.split;
    // Configuración avanzada. Ante un ajuste ausente o corrupto se toma el
    // valor restrictivo: un settings.json a medio escribir no debe terminar
    // en menos restricciones de las que el usuario eligió.
    settings.containImages = s.contain_images !== false;
    settings.blockRemote = s.block_remote !== false;
    settings.trustedDirs = Array.isArray(s.trusted_dirs) ? s.trusted_dirs : [];
    settings.maxDiagrams = parseInt(s.max_diagrams, 10) || 50;
    setTheme(s.theme === 'light' ? 'light' : 'dark');
    setFontSize(parseInt(s.font_size, 10) || 16);
    setTypeface(s.face);
    setToc(!!s.toc);
    const tab = addTab(info.doc, true);
    applyMode(tab, false);
    rerender(true);
    settings.ready = true;
    refreshRecent();
  }

  // El evento pywebviewready puede llegar antes de que se cargue este archivo,
  // por lo que además se sondea el puente hasta que aparezca.
  let booted = false;
  function tryBoot() {
    if (booted || !(window.pywebview && window.pywebview.api
                    && window.pywebview.api.startup)) return;
    booted = true;
    clearInterval(poll);
    boot()
      .then(() => { window.appReady = true; })
      .catch((e) => {
        window.__bootError = (e && e.stack) || String(e);
        toast('No se pudo iniciar: ' + (e && e.message ? e.message : e));
      })
      .finally(() => call('ready').catch(() => {}));
  }
  const poll = setInterval(tryBoot, 60);
  setTimeout(() => clearInterval(poll), 20000);
  window.addEventListener('pywebviewready', tryBoot);
  tryBoot();
})();
