# Visor MD

![Licencia](https://img.shields.io/badge/licencia-GPLv3-blue) ![Plataforma](https://img.shields.io/badge/plataforma-Windows%2010%20%2F%2011-0a7d0a)

Visor y editor de Markdown para Windows. Un único ejecutable de ~14 MB, sin
conexión a internet, que se puede fijar como programa predeterminado para
abrir archivos `.md` fuera de cualquier editor de IA o de código.

**[Descargar VisorMD-portable.zip](../../releases/latest/download/VisorMD-portable.zip)**

## Qué hace

- **Lectura**: el documento renderizado con formato completo — tablas,
  listas de tareas, resaltado de sintaxis, diagramas y fórmulas — con botón
  de copiar en cada bloque de código.
- **Edición**: editor de texto plano con barra de ayudas de formato y
  atajos de teclado, con vista dividida para ver el resultado en vivo.
- **Pestañas y ventanas, como en un navegador**: abrir varios archivos los
  agrega como pestañas de una misma ventana. Se arrastran para reordenarlas,
  se sueltan fuera de la barra para abrirlas en una ventana propia, o sobre
  otra ventana para moverlas ahí.
- **Exporta a PDF** (o a HTML) para compartir el documento renderizado fuera
  de la app.
- Abre también archivos `.txt`, con la opción de convertirlos a `.md`.

## Instalación

### Uso portable (sin instalar nada)

1. Descargar [`VisorMD-portable.zip`](../../releases/latest/download/VisorMD-portable.zip).
2. Descomprimirlo en cualquier carpeta.
3. Ejecutar `VisorMD.exe`. Se puede mover esa carpeta a un pendrive o a otra
   PC sin perder nada: los ajustes se guardan aparte, en el perfil de
   Windows del usuario.

### Instalación en el equipo

1. Descargar y descomprimir `VisorMD-portable.zip` (o usar la carpeta
   `VisorMD` de un release ya descomprimido).
2. Ejecutar `VisorMD.exe` una vez.
3. En el menú `···` de la app, elegir **Instalar en este equipo**. Esto
   copia la aplicación a `%LOCALAPPDATA%\Programs\VisorMD`, crea un acceso
   directo en el menú Inicio y registra las extensiones `.md`, `.markdown`
   y `.txt`. No pide permisos de administrador.
4. Para desinstalarla más adelante: Configuración → Aplicaciones → Visor MD
   → Desinstalar.

### Ponerla como programa predeterminado

Windows no deja que una aplicación se fije a sí misma como predeterminada:
ese paso lo da siempre el usuario, y es el mismo para cualquier programa.

1. Clic derecho sobre un archivo `.md`.
2. **Abrir con** → **Elegir otra aplicación**.
3. Seleccionar **Visor MD** y marcar **Usar siempre esta aplicación para
   abrir archivos .md**.

El primer arranque puede mostrar la advertencia de SmartScreen de Windows
("Windows protegió su PC") porque el ejecutable no tiene una firma de código
comprada: hacer clic en **Más información** → **Ejecutar de todas formas**.

## Todas las funciones

### Atajos de teclado

| Atajo | Acción |
| --- | --- |
| `Ctrl+T` / `Ctrl+W` | Pestaña nueva / cerrar pestaña |
| `Ctrl+Shift+N` | Ventana nueva |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Pestaña siguiente / anterior |
| `Ctrl+R` / `Ctrl+E` | Modo lectura / edición |
| `Ctrl+\` | Vista dividida |
| `Ctrl+S` / `Ctrl+Shift+S` | Guardar / Guardar como |
| `Ctrl+O` | Abrir |
| `Ctrl+F` / `Ctrl+H` | Buscar / Reemplazar |
| `Ctrl+Shift+O` | Índice lateral |
| `Ctrl+D` | Tema nocturno o diurno |
| `Ctrl+P` | Imprimir o guardar en PDF |
| `Ctrl++` / `Ctrl+-` | Tamaño de texto |
| `Ctrl+B` `Ctrl+I` `Ctrl+K` | Negrita, cursiva, enlace |
| `Ctrl+1` a `Ctrl+3` | Títulos H1 a H3 |
| `Ctrl+Shift+` `X` `C` `T` `7` `8` `.` | Tachado, bloque de código, tarea, lista numerada, lista, cita |

En edición, `Enter` continúa la lista actual y la renumera, `Tab` y
`Shift+Tab` indentan la selección, y pegar una URL sobre texto seleccionado
lo convierte en enlace.

### Formato de Markdown admitido

Listas anidadas y numeradas, tablas con alineación, bloques de código dentro
de listas y citas, enlaces inline y de referencia, imágenes locales, HTML,
`<details>`, casillas de verificación, encabezados ATX y setext, escapes,
vallas de código de cuatro backticks y de `~~~`, notas al pie, autolinks,
fórmulas LaTeX (KaTeX), diagramas Mermaid y frontmatter YAML, que se oculta
igual que en GitHub.

### Otras funciones

- **Buscar y reemplazar**, en lectura y en edición.
- **Índice lateral** generado a partir de los encabezados del documento.
- **Archivos recientes** y detección de cambios hechos por otro programa
  mientras el documento está abierto.
- **Imágenes remotas bloqueadas por defecto**: solo se cargan si el usuario
  lo pide desde el menú, para no filtrar la IP al abrir un documento ajeno.
- Tema **nocturno** y **diurno**, y tamaño de letra ajustable.

---

## Detalles técnicos

### Arquitectura

| Archivo | Contenido |
| --- | --- |
| `src/main.py` | Ventanas, pestañas, puente con JavaScript, archivos y ajustes |
| `src/winshell.py` | Instalación, registro de extensiones y desinstalación |
| `src/web/index.html` | Estructura de la interfaz |
| `src/web/styles.css` | Temas y estilos del documento |
| `src/web/render.js` | Markdown a HTML, sanitización y post-proceso |
| `src/web/editor.js` | Ayudas de escritura sobre el área de texto |
| `src/web/app.js` | Estado, pestañas, atajos y llamadas a Python |
| `src/web/vendor/` | markdown-it, highlight.js, KaTeX, Mermaid y DOMPurify |

La interfaz corre sobre WebView2, el motor de Edge que Windows ya incluye,
de modo que el ejecutable no empaqueta un navegador propio. Python se ocupa
de la entrada y salida de archivos, los diálogos nativos y el registro de
Windows; toda la lógica de render y edición vive en JavaScript.

El editor es un `<textarea>` nativo, no un componente de terceros: conserva
el deshacer y rehacer del sistema operativo y evita una dependencia extra.
Mermaid ocupa 3,5 MB de los 4,3 MB de librerías empaquetadas y se carga de
forma diferida, solo cuando el documento contiene un diagrama.

### Pestañas y ventanas

Todas las ventanas de una misma sesión viven en un solo proceso: abrir una
ventana nueva es instantáneo, comparten los ajustes en memoria y mover una
pestaña de una ventana a otra no requiere comunicación entre procesos.

Cada pestaña es un documento independiente (`Doc` en `main.py`) con su ruta,
codificación, fin de línea y estado de cambios sin guardar. La interfaz
mantiene un único `<textarea>` y un único panel de vista previa: cambiar de
pestaña vuelca el texto en memoria y vuelve a renderizar, en vez de sostener
varios pares editor/vista ocultos.

El arrastre de pestañas usa eventos de puntero en vez del arrastrar y
soltar nativo de HTML5, que no ofrece control fino sobre soltar una pestaña
fuera de la ventana o sobre otra ventana de la misma app. Al soltar, se
identifica qué ventana propia hay bajo el cursor: si hay una, la pestaña se
muda con su texto sin guardar; si no hay ninguna, se abre una ventana nueva
en ese punto.

Abrir un archivo con una ventana ya abierta lo agrega como pestaña nueva en
esa ventana, en vez de abrir una segunda.

El aviso de cambios sin guardar al cerrar usa un diálogo propio con el
mismo estilo de la app, no el cuadro nativo de Windows.

### Manejo de archivos

- Codificaciones admitidas: UTF-8, UTF-8 con BOM, UTF-16 con BOM y cp1252.
  La codificación original se detecta y se conserva al guardar.
- Se preservan el BOM y el tipo de fin de línea, CRLF o LF.
- El guardado es atómico: archivo temporal en la misma carpeta y reemplazo,
  para no dejar el archivo a medio escribir ante un corte.
- Si el archivo cambia por fuera de la aplicación, al recuperar el foco se
  ofrece recargarlo.

### Seguridad

Un documento Markdown puede provenir de cualquier origen, así que se trata
como contenido no confiable:

- Todo el HTML generado pasa por DOMPurify. Se eliminan `<script>`, los
  atributos `on*=` y los enlaces `javascript:`, `data:`, `file:` y
  `ms-msdt:`.
- `<style>` y `<form>` se prohíben aparte por su alcance global dentro de la
  página.
- El panel del documento usa `contain: paint`, de modo que un elemento
  posicionado dentro del Markdown no puede cubrir la barra de herramientas.
- Los bloques de código pierden los atributos `style` y `hidden`: lo que se
  copia siempre coincide con lo que se ve.
- Los enlaces del documento no navegan dentro de la aplicación. Solo
  `http`, `https` y `mailto` se abren en el navegador del sistema; el clic
  central se intercepta igual que el clic normal.
- Las imágenes remotas están bloqueadas por defecto. Las locales las
  entrega Python en base64, tras comprobar extensión y tamaño.
- KaTeX corre con `trust: false` y Mermaid con `securityLevel: 'strict'`.
- El registro de Windows se modifica solo en `HKCU` y solo a pedido
  explícito del usuario. Los procesos auxiliares se invocan por ruta
  absoluta, no por nombre.

### Pruebas

Dos suites, sin frameworks de por medio:

- `tests/test_files.py` — lectura y escritura en disco: codificaciones,
  BOM, fin de línea, guardado atómico, detección de cambios externos y
  movimiento de una pestaña entre ventanas.
- `tests/smoke.py` — abre la aplicación real (no un mock) y verifica el
  render contra `tests/estres.md`, un documento armado con casos límite de
  Markdown y contenido deliberadamente hostil (scripts inyectados, enlaces
  `javascript:`, bloques de código con texto oculto) para confirmar que la
  sanitización efectivamente los neutraliza. Cubre también pestañas,
  arrastre entre ventanas y el diálogo de cierre.

El arrastre entre ventanas se verificó además moviendo el cursor del
sistema operativo de verdad, no con eventos simulados.

```powershell
python tests\test_files.py
python tests\smoke.py
```

### Paleta

| Rol | Nocturno | Diurno |
| --- | --- | --- |
| Fondo | `#061401` | `#EBFADC` |
| Superficies | `#0C2206` | `#F7FDEF` |
| Texto | `#E3F6E7` | `#132A0A` |
| Iconos y acento | `#1C9E1C` | `#1C9E1C` |
| Acento sobre texto blanco | `#157815` | `#157815` |

### Desarrollo

```powershell
python -m pip install -r requirements.txt
python src\main.py tests\muestra.md
```

Compilar el ejecutable (genera `dist\VisorMD\` y `dist\VisorMD-portable.zip`):

```powershell
powershell -ExecutionPolicy Bypass -File build\build.ps1
```

Actualizar las librerías del navegador:

```powershell
cd build
npm install markdown-it markdown-it-anchor markdown-it-footnote markdown-it-deflist markdown-it-task-lists "@highlightjs/cdn-assets" mermaid katex dompurify
```

Copiar los `dist/*.min.js` resultantes a `src/web/vendor/`. De las fuentes
de KaTeX se conservan solo los `.woff2`.

## Licencia

[GNU GPLv3](LICENSE) © 2026 [PullAngel](https://github.com/PullAngel)
