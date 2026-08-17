---
title: Frontmatter hostil
__proto__:
  contaminado: true
constructor:
  prototype:
    contaminado: true
ancla: &a ["x", "x", "x", "x", "x", "x", "x", "x", "x"]
b: &b [*a, *a, *a, *a, *a, *a, *a, *a, *a]
c: &c [*b, *b, *b, *b, *b, *b, *b, *b, *b]
d: [*c, *c, *c, *c, *c, *c, *c, *c, *c]
python: !!python/object/apply:os.system ["calc.exe"]
js: !!js/function "function(){ window.__FM = true }"
ruta: ../../../../Windows/System32
profundo: {a: {b: {c: {d: {e: {f: {g: {h: {i: {j: 1}}}}}}}}}}
---

# Frontmatter hostil

El bloque de arriba trae anchors que se expanden entre sí, etiquetas de
deserialización y claves que buscan contaminar el prototipo.

Visor MD no interpreta el frontmatter: lo quita con una expresión regular
antes de pasar el texto al parser, así que no hay ningún analizador de YAML
que pueda expandir nada de eso.

Este párrafo debe verse, y nada del bloque anterior debe aparecer en pantalla.

## Frontmatter que no es el primero del archivo

Un bloque igual en medio del documento sí es contenido, y se muestra como la
línea horizontal y el texto que Markdown dice que es:

---
title: este no es frontmatter
---
