# Suplantación de elementos de la interfaz

El documento se renderiza dentro de la misma página que la interfaz, así que
un `id` repetido puede robarle la referencia a la aplicación. Después de abrir
este archivo, la aplicación tiene que seguir apuntando a sus propios
elementos.

## Elementos de la aplicación, por id

<div id="dialog">falso diálogo</div>
<div id="dlg-body">cuerpo falso</div>
<button id="dlg-ok">Aceptar falso</button>
<button id="dlg-cancel">Cancelar falso</button>
<div id="menu">menú falso</div>
<div id="ctxmenu">menú contextual falso</div>
<div id="tablist">lista de pestañas falsa</div>
<div id="toast">aviso falso</div>
<div id="editor">editor falso</div>
<div id="preview">vista falsa</div>
<div id="findbar">búsqueda falsa</div>
<div id="toc-list">índice falso</div>
<div id="tabs-scroll">pestañas falsas</div>
<div id="switch">conmutador falso</div>
<div id="win-close">cerrar falso</div>

## Por atributo name

<a name="dialog">ancla</a>
<a name="body">ancla</a>
<a name="location">ancla</a>
<a name="document">ancla</a>
<a name="api">ancla</a>

## Nombres globales del navegador

<div id="window">w</div>
<div id="document">d</div>
<div id="location">l</div>
<div id="body">b</div>
<div id="forms">f</div>
<div id="self">s</div>
<div id="top">t</div>

## Nombres internos de la aplicación

<div id="app">a</div>
<div id="render">r</div>
<div id="md">m</div>
<div id="api">i</div>
<div id="Editor">e</div>
<div id="Render">R</div>

## Sin atacante: encabezados que generan los mismos identificadores

Estos son Markdown corriente. El generador de anclas los convierte en `id`,
así que producen la misma colisión sin que nadie lo intente.

## Menú

## Editor

## Dialog

## Preview
