# Diagramas hostiles

Mermaid recibe código que controla el documento y devuelve SVG que se inserta
en la página. Estos diagramas intentan que ese SVG traiga algo activo.

## Acciones de clic y llamadas

```mermaid
graph LR
  A[nodo] --> B[otro]
  click A callback "descripción"
  click B href "javascript:window.__M1=true"
```

## Enlace con protocolo peligroso

```mermaid
graph TD
  X[texto]
  click X "javascript:window.__M2=true"
```

## Etiquetas con HTML

```mermaid
graph LR
  A["<img src=x onerror='window.__M3=true'>"] --> B["<b>negrita</b>"]
```

```mermaid
graph LR
  A["<script>window.__M4=true</script>"]
```

## Recurso remoto dentro del diagrama

```mermaid
graph LR
  A["<img src='https://rastreo.example/m.png'>"]
```

## Estilo inyectado en el diagrama

```mermaid
graph LR
  A[nodo]
  style A fill:url("https://rastreo.example/relleno.png")
```

## Identificador que choca con la interfaz

```mermaid
graph LR
  dialog[dialog] --> menu[menu]
```

## Diagrama válido: debe seguir dibujándose igual

```mermaid
sequenceDiagram
    participant U as Usuario
    participant A as Visor MD
    U->>A: Doble clic en .md
    A-->>U: Documento renderizado
```

```mermaid
graph TD
  Inicio[Abrir archivo] --> Lee{¿Es Markdown?}
  Lee -->|Sí| Render[Renderizar]
  Lee -->|No| Plano[Mostrar como texto]
```
