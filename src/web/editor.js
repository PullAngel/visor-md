/* editor.js — ayudas de escritura sobre el <textarea>.
   Todas las ediciones pasan por execCommand('insertText') para no romper el
   deshacer/rehacer nativo de Windows (Ctrl+Z / Ctrl+Y). */

window.Editor = (function () {
  let ta = null;
  let onChange = () => {};

  const val = () => ta.value;

  function insert(text) {
    ta.focus();
    document.execCommand('insertText', false, text);
    onChange();
  }

  function replaceRange(start, end, text, selStart, selEnd) {
    ta.focus();
    ta.setSelectionRange(start, end);
    document.execCommand('insertText', false, text);
    if (selStart !== undefined) ta.setSelectionRange(selStart, selEnd === undefined ? selStart : selEnd);
    onChange();
  }

  /** Extremos de las líneas completas que toca la selección. */
  function lineBounds() {
    const v = val();
    const start = v.lastIndexOf('\n', ta.selectionStart - 1) + 1;
    let end = v.indexOf('\n', ta.selectionEnd);
    if (end === -1) end = v.length;
    return { start, end, text: v.slice(start, end) };
  }

  /** Envolver la selección, o quitar el envoltorio si ya lo tiene. */
  function surround(pre, post) {
    post = post === undefined ? pre : post;
    const v = val();
    let s = ta.selectionStart;
    let e = ta.selectionEnd;
    const inner = v.slice(s, e);

    if (inner.startsWith(pre) && inner.endsWith(post) && inner.length >= pre.length + post.length) {
      const bare = inner.slice(pre.length, inner.length - post.length);
      replaceRange(s, e, bare, s, s + bare.length);
      return;
    }
    if (v.slice(s - pre.length, s) === pre && v.slice(e, e + post.length) === post) {
      replaceRange(s - pre.length, e + post.length, inner, s - pre.length, e - pre.length);
      return;
    }
    if (s === e) {
      insert(pre + post);
      ta.setSelectionRange(s + pre.length, s + pre.length);
      return;
    }
    replaceRange(s, e, pre + inner + post, s + pre.length, e + pre.length);
  }

  /** Agregar un prefijo a las líneas seleccionadas, o quitarlo si ya lo tienen todas. */
  function prefixLines(make, test) {
    const { start, end, text } = lineBounds();
    const lines = text.split('\n');
    const allHave = lines.every((l) => l.trim() === '' || test(l));
    const out = lines.map((l, i) => {
      if (allHave) return l.replace(/^(\s*)(?:[-*+]\s\[[ xX]\]\s|[-*+]\s|\d+[.)]\s|#{1,6}\s|>\s?)/, '$1');
      if (l.trim() === '' && lines.length > 1) return l;
      const m = l.match(/^(\s*)/)[0];
      return m + make(l.slice(m.length), i);
    });
    const joined = out.join('\n');
    replaceRange(start, end, joined, start, start + joined.length);
  }

  const HEAD = (n) => (line) => '#'.repeat(n) + ' ' + line.replace(/^#{1,6}\s+/, '');

  const ACTIONS = {
    bold: () => surround('**'),
    italic: () => surround('*'),
    strike: () => surround('~~'),
    code: () => surround('`'),
    h1: () => prefixLines(HEAD(1), (l) => /^#\s/.test(l.trim())),
    h2: () => prefixLines(HEAD(2), (l) => /^##\s/.test(l.trim())),
    h3: () => prefixLines(HEAD(3), (l) => /^###\s/.test(l.trim())),
    ul: () => prefixLines((l) => '- ' + l.replace(/^(?:[-*+]\s|\d+[.)]\s)/, ''),
                          (l) => /^[-*+]\s/.test(l.trim())),
    ol: () => prefixLines((l, i) => `${i + 1}. ` + l.replace(/^(?:[-*+]\s|\d+[.)]\s)/, ''),
                          (l) => /^\d+[.)]\s/.test(l.trim())),
    task: () => prefixLines((l) => '- [ ] ' + l.replace(/^(?:[-*+]\s(?:\[[ xX]\]\s)?|\d+[.)]\s)/, ''),
                            (l) => /^[-*+]\s\[[ xX]\]\s/.test(l.trim())),
    quote: () => prefixLines((l) => '> ' + l.replace(/^>\s?/, ''), (l) => /^>/.test(l.trim())),
    link: () => {
      const sel = val().slice(ta.selectionStart, ta.selectionEnd);
      const s = ta.selectionStart;
      if (!sel) { insert('[texto](url)'); ta.setSelectionRange(s + 1, s + 6); return; }
      if (/^https?:\/\/\S+$/i.test(sel)) {
        replaceRange(s, ta.selectionEnd, `[](${sel})`, s + 1, s + 1);
        return;
      }
      replaceRange(s, ta.selectionEnd, `[${sel}](url)`,
                   s + sel.length + 3, s + sel.length + 6);
    },
    image: () => {
      const sel = val().slice(ta.selectionStart, ta.selectionEnd);
      const s = ta.selectionStart;
      const text = `![${sel || 'descripción'}](ruta/imagen.png)`;
      replaceRange(s, ta.selectionEnd, text, s + text.length - 17, s + text.length - 1);
    },
    fence: () => {
      const s = ta.selectionStart;
      const sel = val().slice(s, ta.selectionEnd);
      const nl = s > 0 && val()[s - 1] !== '\n' ? '\n' : '';
      const text = `${nl}\`\`\`\n${sel}\n\`\`\`\n`;
      replaceRange(s, ta.selectionEnd, text, s + nl.length + 3, s + nl.length + 3);
    },
    table: () => {
      const s = ta.selectionStart;
      const nl = s > 0 && val()[s - 1] !== '\n' ? '\n' : '';
      insert(nl + '| Columna 1 | Columna 2 |\n| --- | --- |\n| valor | valor |\n');
    },
    hr: () => {
      const s = ta.selectionStart;
      const nl = s > 0 && val()[s - 1] !== '\n' ? '\n' : '';
      insert(nl + '\n---\n\n');
    },
  };

  function apply(kind) {
    const fn = ACTIONS[kind];
    if (fn) fn();
  }

  /* --- teclado --- */

  const LIST_RE = /^(\s*)(?:([-*+])\s+(\[[ xX]\]\s+)?|(\d+)([.)])\s+)/;

  function handleEnter(e) {
    if (e.shiftKey || ta.selectionStart !== ta.selectionEnd) return false;
    const v = val();
    const pos = ta.selectionStart;
    const lineStart = v.lastIndexOf('\n', pos - 1) + 1;
    const line = v.slice(lineStart, pos);
    const m = line.match(LIST_RE);
    if (!m) return false;

    // Línea con marcador pero sin contenido: Enter sale de la lista.
    if (line.slice(m[0].length).trim() === '') {
      e.preventDefault();
      replaceRange(lineStart, pos, '', lineStart, lineStart);
      return true;
    }
    const marker = m[2]
      ? `${m[1]}${m[2]} ${m[3] ? '[ ] ' : ''}`
      : `${m[1]}${parseInt(m[4], 10) + 1}${m[5]} `;
    e.preventDefault();
    insert('\n' + marker);
    return true;
  }

  function handleTab(e) {
    e.preventDefault();
    const { start, end, text } = lineBounds();
    const multi = ta.selectionStart !== ta.selectionEnd || e.shiftKey;
    if (!multi) { insert('  '); return; }
    const out = text.split('\n')
      .map((l) => (e.shiftKey ? l.replace(/^ {1,2}/, '') : '  ' + l))
      .join('\n');
    replaceRange(start, end, out, start, start + out.length);
  }

  const WRAPPERS = { '*': '*', '_': '_', '`': '`', '"': '"', '(': ')', '[': ']', '{': '}' };

  function onKeydown(e) {
    if (e.key === 'Enter') { handleEnter(e); return; }
    if (e.key === 'Tab') { handleTab(e); return; }
    if (!e.ctrlKey && !e.altKey && !e.metaKey && WRAPPERS[e.key]
        && ta.selectionStart !== ta.selectionEnd) {
      e.preventDefault();
      surround(e.key, WRAPPERS[e.key]);
    }
  }

  function onPaste(e) {
    const text = (e.clipboardData || window.clipboardData).getData('text');
    const sel = val().slice(ta.selectionStart, ta.selectionEnd);
    if (sel && /^https?:\/\/\S+$/i.test(text.trim())) {
      e.preventDefault();
      const s = ta.selectionStart;
      const out = `[${sel}](${text.trim()})`;
      replaceRange(s, ta.selectionEnd, out, s + out.length, s + out.length);
    }
  }

  function init(textarea, changeHandler) {
    ta = textarea;
    onChange = changeHandler || (() => {});
    ta.addEventListener('keydown', onKeydown);
    ta.addEventListener('paste', onPaste);
  }

  return { init, apply, insert, replaceRange, get el() { return ta; } };
})();
