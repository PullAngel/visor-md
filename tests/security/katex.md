# Fórmulas hostiles

KaTeX convierte expresiones que controla el documento en HTML y MathML. Estas
intentan que produzca navegación, contenido activo o un coste desmedido.

## Enlaces y recursos

$\href{javascript:window.__K1=true}{clic}$

$\href{https://rastreo.example/k}{enlace remoto}$

$\url{https://rastreo.example/u}$

$\includegraphics[width=1em]{https://rastreo.example/i.png}$

## Clases e identificadores en la salida

$\htmlClass{tab active}{texto}$

$\htmlId{dialog}{texto}$

$\htmlStyle{position:fixed;inset:0;z-index:99999}{capa}$

$\htmlData{x=1}{texto}$

## Tamaños desmedidos

$\rule{99999em}{99999em}$

$\rule{1em}{50000em}$

$\kern99999em x$

$\hspace{99999em}$

## Expansión de macros

$\def\a{\b\b}\def\b{\c\c}\def\c{\d\d}\def\d{\e\e}\def\e{x}\a$

$\newcommand{\r}{\r}\r$

## Fórmulas válidas: deben seguir viéndose

Inline: $E = mc^2$ y $\sum_{i=1}^{n} i = \frac{n(n+1)}{2}$.

$$
\begin{aligned}
f(x) &= \int_0^x t^2 \, dt \\
     &= \frac{x^3}{3}
\end{aligned}
$$
