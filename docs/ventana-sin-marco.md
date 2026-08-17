# La ventana sin marco

Visor MD dibuja su propia barra de título para que las pestañas ocupen la
misma fila que los botones de minimizar, maximizar y cerrar. Windows no
ofrece eso: o se acepta el marco nativo entero, o se renuncia a él y hay que
reponer a mano todo lo que el marco traía puesto.

Este documento explica qué se pierde al quitar el marco, cómo se repone cada
pieza y qué errores produjo el camino. Sirve para cualquier otra aplicación
que quiera una barra de título propia.

## Qué se rompe al poner `frameless=True`

Una ventana sin `WS_CAPTION` deja de ser, para Windows, una ventana normal.
Desaparecen de golpe cuatro comportamientos que nadie programó porque venían
incluidos:

| Se pierde | Por qué |
| --- | --- |
| Redimensionar desde los bordes | No hay borde grueso que agarrar |
| Acoplar a los lados (Aero Snap) | El gestor de ventanas lo ofrece a ventanas con marco |
| Arrastrar la ventana | No hay barra de título que arrastrar |
| Maximizar respetando la barra de tareas | El tamaño maximizado se calcula a partir de un marco inexistente |

Los cuatro se reponen desde `src/main.py`.

## Bordes y acople: `WS_THICKFRAME`

`restore_resize_border()` vuelve a activar los estilos `WS_THICKFRAME`,
`WS_MAXIMIZEBOX` y `WS_MINIMIZEBOX` sobre la ventana ya creada, con
`SetWindowLongPtrW`. `WS_THICKFRAME` es el estilo que Windows asocia con "esta
ventana se puede redimensionar", y de él dependen tanto el arrastre de bordes
como Aero Snap. Recuperarlo no devuelve la barra de título, que es
`WS_CAPTION`, un estilo distinto.

El cambio de estilos no surte efecto hasta que se le avisa al gestor de
ventanas con `SetWindowPos` y `SWP_FRAMECHANGED`.

## Maximizar sin tapar la barra de tareas: `WM_GETMINMAXINFO`

Al maximizar, Windows calcula el tamaño destino restando el marco al
rectángulo del monitor. Sin marco, esa resta da cero y la ventana termina
ocupando la pantalla completa, tapando la barra de tareas. Visualmente parece
pantalla completa, pero para el sistema sigue siendo una ventana maximizada.

La corrección no está en el botón propio sino en el mensaje que Windows manda
antes de maximizar. `clamp_maximize_to_work_area()` intercepta
`WM_GETMINMAXINFO` y escribe en la estructura `MINMAXINFO` el rectángulo
`rcWork` del monitor, que es la pantalla menos las barras acopladas.

Interceptar el mensaje, y no el botón, es lo que hace que la corrección valga
para todas las vías de maximizar: el botón propio, `Win+Flecha arriba`, el
acople al borde superior y cualquier otra que agregue Windows más adelante.
Corregir solo el botón habría dejado las demás rotas.

Dos detalles que cuestan un rato descubrir:

- `ptMaxPosition` es **relativo al monitor**, no al escritorio. En un
  monitor secundario hay que restarle el origen de `rcMonitor`.
- Si no se toca `ptMaxTrackSize`, el usuario no puede agrandar la ventana a
  mano más allá del tamaño maximizado, porque ese campo también fija el
  máximo del redimensionado manual.

Para interceptar el mensaje hay que sustituir el procedimiento de ventana con
`SetWindowLongPtrW(GWL_WNDPROC)` y encadenar el anterior con
`CallWindowProcW`. El puntero al procedimiento nuevo se guarda en un
diccionario del módulo: si el recolector de basura se lo lleva, Windows queda
apuntando a memoria liberada y la aplicación cae al primer mensaje.

## Pantalla completa de verdad

Como el maximizado ahora respeta la barra de tareas, la pantalla completa
necesita su propio camino: `toggle_fullscreen()` no usa el estado maximizado
de Windows, sino que coloca la ventana sobre `rcMonitor` —el rectángulo
completo— y guarda la posición anterior para poder volver. Está en el menú
`···` y en `F11`.

Son dos estados distintos a propósito: maximizado respeta el escritorio,
pantalla completa lo tapa, y el usuario elige.

## El error del botón de cerrar

Minimizar y maximizar funcionaban; cerrar no hacía nada, por más veces que se
pulsara. La causa no estaba en la ventana sino en el puente entre JavaScript y
Python:

```js
$('win-close').addEventListener('click', () => call('close_window').catch(() => {}));
```

`close_window` nunca se implementó del lado de Python. La llamada fallaba, y
el `.catch(() => {})` se tragaba el error sin dejar rastro: ni excepción, ni
mensaje en consola, ni pista visible. El botón quedaba mudo.

El `.catch` vacío es correcto para llamadas cuyo fallo no importa —guardar una
preferencia, refrescar la lista de recientes—, pero convierte un método
inexistente en un botón que no responde. Un puente dinámico como el de
pywebview no avisa de métodos que faltan: no hay compilador ni tipos que los
detecten.

La lección aplicable a cualquier puente entre dos lenguajes: **el silencio no
es ausencia de error**. Cuando una acción de la interfaz no ocurre y tampoco
hay error, el primer sospechoso es el manejador que descarta el error.

La prueba de regresión que quedó no comprueba que la ventana cierre, sino algo
más general: lee `app.js`, extrae todos los nombres que pasan por `call(...)` y
verifica que cada uno exista como método en Python. Un método que se renombre
de un lado y no del otro falla el test antes de llegar a la interfaz.

```python
llamadas = set(re.findall(r"call\(\s*'([a-z_]+)'", js))
faltan = sorted(n for n in llamadas if not callable(getattr(api, n, None)))
```

## Por qué cerrar pasa por `destroy()`

`close_window()` llama a `self._window.destroy()` y no a `force_close()`. La
diferencia importa: `destroy()` dispara el evento `closing`, que es donde se
comprueba si hay pestañas sin guardar y se muestra el aviso. Saltearlo habría
cerrado la ventana perdiendo cambios sin preguntar.

El botón propio y el cierre nativo terminan así en el mismo camino, con una
sola implementación del aviso.
