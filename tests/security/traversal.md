# Salida de la carpeta del documento

Cada imagen pide un archivo fuera de la carpeta de este documento. Ninguna
debe cargarse mientras la contención esté activada, y las de red no deben
cargarse nunca, ni siquiera con el permiso dado.

## Subir por la jerarquía

![relativa](../../assets/visormd.png)

![muchos niveles](../../../../../../Windows/System32/oobe/BackgroundDefault.jpg)

![con punto](./../../assets/visormd.png)

## Codificada

![porciento](%2e%2e%2f%2e%2e%2fassets%2fvisormd.png)

![mezclada](..%2f..%2fassets%2fvisormd.png)

## Absolutas

![unidad barra invertida](C:\Windows\System32\oobe\BackgroundDefault.jpg)

![unidad barra normal](C:/Windows/System32/oobe/BackgroundDefault.jpg)

![sin unidad](/Windows/System32/oobe/BackgroundDefault.jpg)

## Red: bloqueadas siempre

![UNC](\\servidor.example\recurso\imagen.png)

![UNC con barras normales](//servidor.example/recurso/imagen.png)

![ruta de dispositivo](\\?\C:\Windows\System32\oobe\BackgroundDefault.jpg)

![dispositivo punto](\\.\C:\Windows\System32\oobe\BackgroundDefault.jpg)

## Flujo alternativo de NTFS

![flujo](imagen.png:oculto)

![flujo con tipo](imagen.png:oculto:$DATA)

## Dentro de la carpeta: debe cargarse

![propia](propia.png)

![en subcarpeta](medios/propia.png)
