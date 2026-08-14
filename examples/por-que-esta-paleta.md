# Por qué esta paleta

La mayoría de los editores de texto para la noche usan grises azulados o
un violeta genérico. Quería algo distinto: un verde casi negro que se
sintiera más a bosque de noche que a pantalla de oficina, y un verde hueso
para el día que no encandilara a la mañana.

## La combinación

| Rol | Nocturno | Diurno |
| --- | --- | --- |
| Fondo | `#061401` | `#EBFADC` |
| Superficies | `#0C2206` | `#F7FDEF` |
| Texto | `#E3F6E7` | `#132A0A` |
| Acento | `#1C9E1C` | `#1C9E1C` |

El mismo verde de acento funciona en los dos temas porque los fondos están
en extremos opuestos de luminosidad: sobre el fondo casi negro resalta como
un semáforo, sobre el hueso pálido queda firme sin gritar.

## En la práctica

El acento no se usa igual en todos lados. Como texto o borde alcanza con el
verde base; como fondo detrás de una etiqueta blanca hace falta una versión
más oscura, si no el contraste no llega a un nivel legible:

```css
:root {
  --accent: #1C9E1C;        /* texto, bordes, íconos */
  --accent-strong: #157815; /* fondo bajo texto blanco */
}
```

Separar esos dos casos evitó el problema más común de elegir un solo verde
"lindo" y después pelear con la legibilidad en cada componente por separado.

## Inspiración

Musgo, hojas de helecho a contraluz, y el cartel de neón verde de una
farmacia de barrio a las tres de la mañana.
