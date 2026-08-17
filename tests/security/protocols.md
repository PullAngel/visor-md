# Protocolos de URL

Cada enlace usa un esquema distinto. Ninguno debe sobrevivir salvo http,
https y mailto; el resto tiene que quedar sin `href` o inerte.

## Permitidos

[http](http://example.com/pagina)
[https](https://example.com/pagina)
[mailto](mailto:alguien@example.com)
[ancla interna](#permitidos)
[documento relativo](./otro.md)

## Ejecución de guiones

[javascript](javascript:window.__P1=true)
[JaVaScRiPt](JaVaScRiPt:window.__P2=true)
[javascript con espacio](java script:window.__P3=true)
[javascript codificado](javascript%3Awindow.__P4=true)
[vbscript](vbscript:MsgBox("x"))
[data html](data:text/html;base64,PHNjcmlwdD53aW5kb3cuX19QNT10cnVlPC9zY3JpcHQ+)
[data svg](data:image/svg+xml,<svg onload="window.__P6=true"/>)

## Acceso local y protocolos de Windows

[file unidad](file:///C:/Windows/System32/drivers/etc/hosts)
[file recurso](file://servidor/recurso/x.txt)
[ms-msdt](ms-msdt:/id%20PCWDiagnostic)
[ms-officecmd](ms-officecmd:%7B%22id%22:3%7D)
[search-ms](search-ms:query=contraseña&crumb=location:C%3A%5C)
[shell](shell:Startup)
[ms-settings](ms-settings:windowsupdate)
[ruta UNC](\\servidor.example\recurso\documento.md)

## Esquemas que la aplicación no usa

[tel](tel:+541100000000)
[sms](sms:+541100000000)
[ftp](ftp://example.com/archivo.txt)
[xmpp](xmpp:alguien@example.com)
[cid](cid:parte-del-mensaje)
[inventado](protocoloinventado:carga)
