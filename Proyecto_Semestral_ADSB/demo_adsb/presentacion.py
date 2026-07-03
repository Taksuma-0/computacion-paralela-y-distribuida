#!/usr/bin/env python3
"""Builder de la presentacion HTML autocontenida (offline), patron de adsb_report.py.

Lee los assets del sistema real (SVG del dashboard TUI, PNGs de los graficos) y los
incrusta (SVG inline, PNG->base64 data URI) en una plantilla con motor de diapositivas.
Salida: ../presentacion_final.html (un unico archivo que abre por doble clic).

Uso:  python presentacion.py
"""
import base64
import os
import re

DEMO = os.path.dirname(os.path.abspath(__file__))
GRAF = os.path.join(DEMO, "results", "graficos")
OUT = os.path.join(os.path.dirname(DEMO), "presentacion_final.html")


def _b64(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")


def _svg_inline(path):
    with open(path, encoding="utf-8") as f:
        s = f.read()
    i = s.find("<svg")
    s = s[i:] if i >= 0 else s
    # el SVG de Textual referencia una fuente web (cdnjs): quitarla para que sea OFFLINE
    s = re.sub(r"@font-face\s*\{[^}]*\}", "", s)
    s = re.sub(r"https?://[^\s\"')<>]+", "", s)
    return s


def build():
    tui = _svg_inline(os.path.join(GRAF, "tui_dashboard.svg"))
    speedup = _b64(os.path.join(GRAF, "speedup.png"))
    efic = _b64(os.path.join(GRAF, "eficiencia.png"))
    html = (PLANTILLA
            .replace("__TUI_SVG__", tui)
            .replace("__SPEEDUP_PNG__", speedup)
            .replace("__EFICIENCIA_PNG__", efic))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("Presentacion ->", OUT, f"({os.path.getsize(OUT)//1024} KB)")


PLANTILLA = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ADS-B · Presentación</title>
<style>
:root{
  --void:#04100a; --panel:#06170e; --panel2:#08200f; --grid:#124a2c; --grid2:#0c2c1b;
  --phos:#39ff7a; --phos-dim:#1f8f4d; --ink:#bfe9cf; --ink-dim:#5f8a72; --paper:#e9fbef;
  --blue:#3fa7ff; --amber:#ffb000; --red:#ff5247; --violet:#c77dff;
  --mono:ui-monospace,"Cascadia Code","Consolas","Liberation Mono",monospace;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{height:100%}
body{background:radial-gradient(1400px 800px at 50% -10%,#0a2417,var(--void) 60%),var(--void);
  color:var(--ink);font-family:var(--mono);overflow:hidden;letter-spacing:.02em}
.scanlines{position:fixed;inset:0;pointer-events:none;z-index:80;opacity:.22;
  background:repeating-linear-gradient(0deg,transparent 0 2px,rgba(0,0,0,.16) 2px 3px)}
.vignette{position:fixed;inset:0;pointer-events:none;z-index:79;
  background:radial-gradient(120% 90% at 50% 42%,transparent 55%,rgba(0,0,0,.6) 100%)}

/* progress + chrome */
.bar{position:fixed;top:0;left:0;height:3px;background:linear-gradient(90deg,var(--phos-dim),var(--phos));
  z-index:90;transition:width .35s ease;box-shadow:0 0 10px var(--phos)}
.counter{position:fixed;bottom:12px;right:16px;z-index:90;font-size:12px;color:var(--ink-dim);letter-spacing:.14em}
.counter b{color:var(--paper)}
.hint{position:fixed;bottom:12px;left:16px;z-index:90;font-size:10px;color:var(--ink-dim);letter-spacing:.12em}
.brandmini{position:fixed;top:12px;left:16px;z-index:90;font-size:11px;letter-spacing:.2em;color:var(--phos-dim)}

/* slides */
.deck{position:fixed;inset:0}
.slide{position:absolute;inset:0;display:none;flex-direction:column;justify-content:center;
  padding:5vh 7vw 8vh;z-index:1}
.slide.active{display:flex}
.rubric{position:absolute;top:4.5vh;right:7vw;font-size:11px;letter-spacing:.14em;color:var(--void);
  background:var(--phos);border-radius:999px;padding:3px 12px;font-weight:700}
.rubric.dim{background:var(--grid);color:var(--phos)}
h1.t{font-size:clamp(22px,3.6vw,44px);color:var(--paper);letter-spacing:.02em;line-height:1.08;font-weight:800}
h2.t{font-size:clamp(19px,2.7vw,34px);color:var(--paper);letter-spacing:.03em;margin-bottom:1.4vh;font-weight:700}
h2.t .pf{color:var(--phos)}
.lead{font-size:clamp(13px,1.5vw,18px);color:var(--ink);line-height:1.5;max-width:60ch}
.pts{list-style:none;display:flex;flex-direction:column;gap:1.1vh;margin-top:1.6vh;font-size:clamp(13px,1.45vw,18px)}
.pts li{color:var(--ink);padding-left:1.5em;text-indent:-1.5em}
.pts li::before{content:"▸ ";color:var(--phos)}
.pts li b{color:var(--paper)}
.hot{color:var(--phos)} .amber{color:var(--amber)}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:4vw;align-items:center}
.center{align-items:center;text-align:center}
.grow{display:flex;gap:14px;flex-wrap:wrap;margin-top:2vh}

/* entrance animation */
.slide.active [data-anim]{opacity:0;transform:translateY(16px);animation:rise .55s cubic-bezier(.2,.7,.2,1) forwards;
  animation-delay:calc(var(--d,0)*90ms)}
@keyframes rise{to{opacity:1;transform:none}}

/* KPI */
.kpi{border:1px solid var(--grid);border-radius:14px;padding:2.2vh 2vw;background:linear-gradient(180deg,var(--panel2),var(--panel));text-align:center;min-width:150px}
.kpi .n{font-size:clamp(30px,5vw,64px);font-weight:800;color:var(--phos);line-height:.9;text-shadow:0 0 24px rgba(57,255,122,.45)}
.kpi .n .u{font-size:.42em;color:var(--phos-dim)}
.kpi .l{font-size:11px;letter-spacing:.16em;color:var(--ink-dim);margin-top:8px}

/* chips / mini scopes */
.chips{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:2vh}
.chip{border:1px solid var(--grid2);border-radius:12px;padding:10px;background:rgba(6,23,14,.6);text-align:center}
.chip svg{width:100%;height:9vh;display:block}
.chip .k{font-size:12px;font-weight:700;letter-spacing:.08em;margin-top:6px}

/* code */
pre.code{border:1px solid var(--grid2);border-radius:10px;background:rgba(4,16,10,.8);color:var(--ink);
  padding:14px 16px;font-size:clamp(11px,1.15vw,15px);line-height:1.5;overflow:auto}
pre.code b{color:var(--phos)} pre.code .c{color:var(--ink-dim)}

/* table */
table.tb{border-collapse:collapse;font-size:clamp(12px,1.3vw,17px);width:100%}
table.tb th,table.tb td{padding:7px 12px;border-bottom:1px solid var(--grid2);text-align:center}
table.tb th{color:var(--phos-dim);font-weight:700;letter-spacing:.08em}
table.tb td b{color:var(--phos)}

/* images */
.foto{border:1px solid var(--grid);border-radius:12px;overflow:hidden;background:#000;box-shadow:0 10px 40px rgba(0,0,0,.5)}
.foto svg,.foto img{display:block;width:100%;height:auto}
.cap{font-size:11px;color:var(--ink-dim);letter-spacing:.1em;margin-top:8px;text-align:center}

/* créditos de portada */
.credits{text-align:center;margin-top:2.6vh}
.credits .crew{display:inline-block;font-size:clamp(14px,1.55vw,20px);color:var(--paper);font-weight:700;letter-spacing:.05em;
  border:1px solid var(--grid);border-radius:999px;padding:9px 24px;
  background:linear-gradient(180deg,rgba(8,32,15,.75),rgba(6,23,14,.45));box-shadow:0 0 28px rgba(57,255,122,.14)}
.credits .crew span{color:var(--phos);margin:0 12px;font-weight:400}
.credits .meta{font-size:11px;color:var(--ink-dim);letter-spacing:.2em;text-transform:uppercase;margin-top:13px}
.credits .meta b{color:var(--phos-dim)}

/* radar mini */
.radar{position:relative;width:min(38vh,340px);aspect-ratio:1/1;margin:auto}
.radar svg{position:absolute;inset:0;width:100%;height:100%}
.sweepwrap{position:absolute;inset:0;border-radius:50%;overflow:hidden}
.sweep{position:absolute;inset:0;border-radius:50%;mix-blend-mode:screen;
  background:conic-gradient(from var(--a,0deg),transparent 0 300deg,rgba(57,255,122,.12) 350deg,rgba(120,255,180,.5) 359deg,transparent 360deg);
  animation:spin 4.2s linear infinite}
@keyframes spin{to{--a:360deg}}
@property --a{syntax:'<angle>';inherits:false;initial-value:0deg}

@media(prefers-reduced-motion:reduce){.sweep{animation:none}.slide.active [data-anim]{animation:none;opacity:1;transform:none}}
</style>
</head>
<body>
<div class="scanlines"></div><div class="vignette"></div>
<div class="bar" id="bar"></div>
<div class="brandmini">ADS-B ANOMALY SCOPE</div>
<div class="counter"><b id="cur">1</b> / <span id="tot">11</span></div>
<div class="hint">← →  navegar · F pantalla completa</div>

<div class="deck" id="deck">

<!-- 1 PORTADA -->
<section class="slide center" data-notes="Presentarnos y la frase del problema en una linea. Somos el grupo X; construimos un sistema que detecta vuelos anomalos de forma DISTRIBUIDA y medimos si acelera.">
  <div class="radar" data-anim style="--d:0">
    <svg viewBox="0 0 300 300">
      <circle cx="150" cy="150" r="146" fill="none" stroke="#124a2c"/>
      <circle cx="150" cy="150" r="100" fill="none" stroke="#0c2c1b"/>
      <circle cx="150" cy="150" r="54" fill="none" stroke="#0c2c1b"/>
      <line x1="4" y1="150" x2="296" y2="150" stroke="#0c2c1b"/><line x1="150" y1="4" x2="150" y2="296" stroke="#0c2c1b"/>
      <polygon points="150,60 156,74 150,70 144,74" fill="#39ff7a"/>
      <polygon points="205,180 212,192 205,188 199,193" fill="#3fa7ff"/>
      <polygon points="95,205 101,218 95,213 89,219" fill="#ffb000"/>
      <circle cx="150" cy="150" r="2.5" fill="#39ff7a"/>
    </svg>
    <div class="sweepwrap"><div class="sweep"></div></div>
  </div>
  <h1 class="t" data-anim style="--d:1">Detección distribuida de anomalías<br>en trayectorias <span style="color:var(--phos)">ADS-B</span></h1>
  <p class="lead" data-anim style="--d:2">Orquestador coordinador–agentes evaluado en local y en clúster QEMU</p>
  <div class="credits" data-anim style="--d:3">
    <div class="crew">Welinton Barrera<span>·</span>Joaquin Araya<span>·</span>Juan Toledo</div>
    <div class="meta"><b>INF8090</b> · Computación Paralela y Distribuida · UTEM · Prof. M. Miranda</div>
  </div>
</section>

<!-- 2 PROBLEMA -->
<section class="slide" data-rubric="Delimitación · 10%" data-notes="El problema: dentro del trafico normal hay vuelos con comportamiento anomalo. Explicar los 4 tipos senalando los mini-radares. Es un problema de ciencia de datos: feature engineering + outlier scoring, no ingenieria plana.">
  <h2 class="t" data-anim style="--d:0">El problema: <span class="pf">vuelos que se salen del patrón</span></h2>
  <p class="lead" data-anim style="--d:1">Las aeronaves emiten su estado por ADS-B. Dentro del tráfico normal hay <b>anomalías de comportamiento</b> que conviene detectar y rankear (seguridad operacional, auditoría de rutas).</p>
  <div class="chips">
    <div class="chip" data-anim style="--d:2"><svg viewBox="0 0 100 60"><path d="M6,30 C35,6 65,6 94,30" fill="none" stroke="#3fd0ff" stroke-width="2.5"/></svg><div class="k" style="color:#3fd0ff">RODEO</div></div>
    <div class="chip" data-anim style="--d:3"><svg viewBox="0 0 100 60"><path d="M6,50 L40,50 C58,50 58,20 40,20 C22,20 22,40 40,40 L94,10" fill="none" stroke="#ffb000" stroke-width="2.5"/></svg><div class="k" style="color:#ffb000">HOLDING</div></div>
    <div class="chip" data-anim style="--d:4"><svg viewBox="0 0 100 60"><path d="M6,14 L50,16 L94,54" fill="none" stroke="#ff5247" stroke-width="2.5"/></svg><div class="k" style="color:#ff5247">DESCENSO</div></div>
    <div class="chip" data-anim style="--d:5"><svg viewBox="0 0 100 60"><path d="M6,20 L45,50 L94,14" fill="none" stroke="#c77dff" stroke-width="2.5"/></svg><div class="k" style="color:#c77dff">GO-AROUND</div></div>
  </div>
</section>

<!-- 3 JUSTIFICACION -->
<section class="slide" data-rubric="Justificación · 15%" data-notes="Por que distribuir: el scoring es independiente por vuelo (embarrassingly-parallel). Una vez extraidas las features, cada particion se procesa sin dependencias. A volumen grande, secuencial no termina. La granularidad decide si conviene.">
  <h2 class="t" data-anim style="--d:0">¿Por qué distribuir?</h2>
  <div class="cols">
    <ul class="pts">
      <li data-anim style="--d:1"><b>Scoring independiente por vuelo</b> → <span class="hot">embarrassingly-parallel</span> sobre particiones.</li>
      <li data-anim style="--d:2">Sin dependencias entre trozos: se reparten y se reducen al final.</li>
      <li data-anim style="--d:3">A volumen grande, la versión <b>secuencial no termina</b> en tiempo razonable.</li>
      <li data-anim style="--d:4">La <b>granularidad</b> decide si el reparto vale la pena.</li>
    </ul>
    <div data-anim style="--d:2">
      <svg viewBox="0 0 300 200" style="width:100%">
        <rect x="120" y="10" width="60" height="26" rx="5" fill="#08200f" stroke="#124a2c"/><text x="150" y="27" fill="#bfe9cf" font-size="11" text-anchor="middle" font-family="monospace">datos</text>
        <g stroke="#1f8f4d" fill="none"><line x1="150" y1="36" x2="60" y2="90"/><line x1="150" y1="36" x2="150" y2="90"/><line x1="150" y1="36" x2="240" y2="90"/></g>
        <g font-family="monospace" font-size="10" text-anchor="middle">
          <rect x="30" y="90" width="60" height="24" rx="5" fill="#06170e" stroke="#1f8f4d"/><text x="60" y="106" fill="#39ff7a">run</text>
          <rect x="120" y="90" width="60" height="24" rx="5" fill="#06170e" stroke="#1f8f4d"/><text x="150" y="106" fill="#39ff7a">run</text>
          <rect x="210" y="90" width="60" height="24" rx="5" fill="#06170e" stroke="#1f8f4d"/><text x="240" y="106" fill="#39ff7a">run</text>
        </g>
        <g stroke="#3fa7ff" fill="none" stroke-dasharray="3 3"><line x1="60" y1="114" x2="150" y2="164"/><line x1="150" y1="114" x2="150" y2="164"/><line x1="240" y1="114" x2="150" y2="164"/></g>
        <rect x="110" y="164" width="80" height="26" rx="5" fill="#08200f" stroke="#3fa7ff"/><text x="150" y="181" fill="#bfe9cf" font-size="11" text-anchor="middle" font-family="monospace">ranking</text>
      </svg>
      <div class="cap">particionar → procesar en paralelo → reducir</div>
    </div>
  </div>
</section>

<!-- 4 DATOS -->
<section class="slide" data-rubric="Datos / Línea base" data-notes="Datos: 636 vuelos reales de OpenSky. Para medir escalabilidad usamos datos-por-semilla: la particion lleva la semilla y el agente regenera -> transferencia casi cero. Linea base secuencial: mismo resultado exacto (equivalencia) -> podemos reportar speedup.">
  <h2 class="t" data-anim style="--d:0">Datos y línea base</h2>
  <div class="cols">
    <ul class="pts">
      <li data-anim style="--d:1"><b>636 vuelos reales</b> de OpenSky Network (ADS-B), resampleados a 40 puntos.</li>
      <li data-anim style="--d:2"><b>Datos-por-semilla</b> (carga densa): la partición lleva la semilla; el agente regenera → <span class="hot">transferencia ≈ 0</span>.</li>
      <li data-anim style="--d:3"><b>Línea base secuencial</b>: mismo contrato en un proceso, mide T₁.</li>
      <li data-anim style="--d:4"><b>Equivalencia verificada</b>: distribuido = secuencial (mismo ranking) → speedup legítimo.</li>
    </ul>
    <div class="kpi" data-anim style="--d:2"><div class="n">636</div><div class="l">VUELOS REALES · OpenSky</div></div>
  </div>
</section>

<!-- 5 ARQUITECTURA -->
<section class="slide" data-rubric="Diseño técnico · 20%" data-notes="Arquitectura: coordinador en el host reparte trozos por TCP a los agentes (paquetes verdes). Cada agente ejecuta run en paralelo. Los resultados vuelven (azul) y merge los reduce. Cola dinamica = balanceo. Tolerancia a fallos: nodo caido -> se excluye y el resto completa.">
  <h2 class="t" data-anim style="--d:0">Arquitectura: <span class="pf">coordinador ⇄ agentes</span></h2>
  <div class="cols">
    <div data-anim style="--d:1">
      <svg viewBox="0 0 600 330" style="width:100%">
        <rect x="220" y="14" width="160" height="54" rx="8" fill="#08200f" stroke="#004E9A" stroke-width="1.5"/>
        <text x="300" y="38" fill="#e9fbef" font-size="15" text-anchor="middle" font-family="monospace" font-weight="bold">COORDINADOR</text>
        <text x="300" y="56" fill="#5f8a72" font-size="11" text-anchor="middle" font-family="monospace">cola dinámica</text>
        <g font-family="monospace" font-size="13" text-anchor="middle" font-weight="bold">
          <rect x="60" y="250" width="120" height="52" rx="8" fill="#06170e" stroke="#7AB830"/><text x="120" y="281" fill="#7AB830">agente 1</text>
          <rect x="240" y="250" width="120" height="52" rx="8" fill="#06170e" stroke="#7AB830"/><text x="300" y="281" fill="#7AB830">agente 2</text>
          <rect x="420" y="250" width="120" height="52" rx="8" fill="#06170e" stroke="#7AB830"/><text x="480" y="281" fill="#7AB830">agente N</text>
        </g>
        <g stroke="#1f8f4d" fill="none" stroke-width="1.2">
          <path id="p1" d="M300,68 L120,250"/><path id="p2" d="M300,68 L300,250"/><path id="p3" d="M300,68 L480,250"/></g>
        <g stroke="#3fa7ff" fill="none" stroke-width="1.2" stroke-dasharray="4 4" opacity=".6">
          <path id="r1" d="M120,250 L300,68"/><path id="r3" d="M480,250 L300,68"/></g>
        <!-- paquetes tarea (verde, bajan) -->
        <circle r="5" fill="#39ff7a"><animateMotion dur="1.5s" repeatCount="indefinite" begin="0s"><mpath href="#p1"/></animateMotion></circle>
        <circle r="5" fill="#39ff7a"><animateMotion dur="1.5s" repeatCount="indefinite" begin="0.5s"><mpath href="#p2"/></animateMotion></circle>
        <circle r="5" fill="#39ff7a"><animateMotion dur="1.5s" repeatCount="indefinite" begin="0.9s"><mpath href="#p3"/></animateMotion></circle>
        <!-- paquetes resultado (azul, suben) -->
        <circle r="4" fill="#3fa7ff"><animateMotion dur="1.7s" repeatCount="indefinite" begin="0.8s"><mpath href="#r1"/></animateMotion></circle>
        <circle r="4" fill="#3fa7ff"><animateMotion dur="1.7s" repeatCount="indefinite" begin="1.4s"><mpath href="#r3"/></animateMotion></circle>
        <text x="300" y="170" fill="#5f8a72" font-size="12" text-anchor="middle" font-family="monospace">TCP · JSON</text>
      </svg>
    </div>
    <ul class="pts">
      <li data-anim style="--d:2"><b class="hot">split</b> reparte trozos por TCP desde una cola dinámica.</li>
      <li data-anim style="--d:3"><b class="hot">run</b> ejecuta en paralelo en cada agente (verde = tarea).</li>
      <li data-anim style="--d:4"><b style="color:#3fa7ff">merge</b> reduce los parciales → ranking global (azul = resultado).</li>
      <li data-anim style="--d:5"><b>Tolerancia a fallos</b>: nodo caído → se excluye, el resto completa.</li>
    </ul>
  </div>
</section>

<!-- 6 IMPLEMENTACION -->
<section class="slide" data-rubric="Implementación · 15%" data-notes="La plataforma es agnostica al dominio: la tarea implementa un contrato minimo. Decisiones: procesos (no hilos) para evitar el GIL; datos-por-semilla para medir computo y no red; scoring z-robusto con MAD y piso por feature para datos reales heterogeneos.">
  <h2 class="t" data-anim style="--d:0">Implementación: contrato enchufable</h2>
  <div class="cols">
    <pre class="code" data-anim style="--d:1"><span class="c"># la plataforma no conoce el dominio</span>
<b>split</b>(payload, workers) -> [chunk...]  <span class="c"># particiona</span>
<b>run</b>(chunk)              -> parcial      <span class="c"># en el agente</span>
<b>merge</b>(parciales)        -> ranking      <span class="c"># reducción</span>
<b>self_test</b>()             -> sonda salud  <span class="c"># health-check</span></pre>
    <ul class="pts">
      <li data-anim style="--d:2"><b>Procesos, no hilos</b> → evitan el <span class="amber">GIL</span> (cómputo real en paralelo).</li>
      <li data-anim style="--d:3"><b>Datos-por-semilla</b> → mide cómputo, no red.</li>
      <li data-anim style="--d:4"><b>Scoring z-robusto (MAD)</b> con piso por feature → robusto a datos reales.</li>
    </ul>
  </div>
</section>

<!-- 7 EVALUACION -->
<section class="slide" data-rubric="Evaluación experimental · 20%" data-notes="Protocolo riguroso: p=1,2,4,8 con 3 repeticiones + calentamiento; media, desviacion y mejor de tres; semilla fija. El speedup crece hasta 5.59 con 8 nodos; la eficiencia baja a 0.70 por overhead. Senalar la curva.">
  <h2 class="t" data-anim style="--d:0">Evaluación experimental</h2>
  <div class="cols">
    <div data-anim style="--d:1">
      <svg viewBox="0 0 320 210" style="width:100%">
        <line x1="34" y1="180" x2="310" y2="180" stroke="#124a2c"/><line x1="34" y1="12" x2="34" y2="180" stroke="#124a2c"/>
        <polyline points="34,168 126,120 218,72 300,24" fill="none" stroke="#888" stroke-width="1.4" stroke-dasharray="4 4"/>
        <text x="292" y="18" fill="#888" font-size="10">ideal</text>
        <polyline id="spline" points="34,168 126,138 218,96 300,55" fill="none" stroke="#39ff7a" stroke-width="3" style="filter:drop-shadow(0 0 5px #39ff7a)"/>
        <g fill="#39ff7a"><circle cx="34" cy="168" r="4"/><circle cx="126" cy="138" r="4"/><circle cx="218" cy="96" r="4"/><circle cx="300" cy="55" r="4"/></g>
        <g fill="#5f8a72" font-size="10" font-family="monospace"><text x="34" y="196" text-anchor="middle">1</text><text x="126" y="196" text-anchor="middle">2</text><text x="218" y="196" text-anchor="middle">4</text><text x="300" y="196" text-anchor="middle">8</text></g>
        <text x="170" y="208" fill="#5f8a72" font-size="10" text-anchor="middle" font-family="monospace">nodos p</text>
        <text x="14" y="96" fill="#5f8a72" font-size="10" font-family="monospace" transform="rotate(-90 14 96)">speedup</text>
      </svg>
      <div class="cap">3 repeticiones + calentamiento · media, desv. y mejor-de-3</div>
    </div>
    <div>
      <table class="tb" data-anim style="--d:2">
        <tr><th>p</th><th>Tₚ (s)</th><th>Sₚ</th><th>Eₚ</th></tr>
        <tr><td>1</td><td>12,96</td><td>1,00</td><td>1,00</td></tr>
        <tr><td>2</td><td>7,35</td><td>1,77</td><td>0,89</td></tr>
        <tr><td>4</td><td>4,19</td><td>3,11</td><td>0,78</td></tr>
        <tr><td>8</td><td>2,33</td><td><b>5,59</b></td><td>0,70</td></tr>
      </table>
      <div class="grow" data-anim style="--d:3"><div class="kpi"><div class="n" data-count="5.59">0<span class="u">×</span></div><div class="l">SPEEDUP · 8 NODOS</div></div></div>
    </div>
  </div>
</section>

<!-- 8 CALIDAD -->
<section class="slide" data-rubric="Evaluación · calidad" data-notes="Calidad: sobre los datos reales, con 12 anomalias inyectadas para validar, recall = 1.0 (las detecta todas) y ademas encontro 8 vuelos reales genuinamente raros. Corrida en el cluster QEMU real con nodo1 y nodo2.">
  <h2 class="t" data-anim style="--d:0">Calidad de la detección</h2>
  <div class="cols">
    <div class="radar" data-anim style="--d:1">
      <svg viewBox="0 0 300 300">
        <circle cx="150" cy="150" r="146" fill="none" stroke="#124a2c"/><circle cx="150" cy="150" r="100" fill="none" stroke="#0c2c1b"/><circle cx="150" cy="150" r="54" fill="none" stroke="#0c2c1b"/>
        <path d="M60,90 C120,60 180,80 240,120" fill="none" stroke="#ffb000" stroke-width="2.4"/>
        <path d="M90,210 C140,150 170,150 220,200" fill="none" stroke="#3fd0ff" stroke-width="2.4"/>
        <path d="M120,240 L170,120" fill="none" stroke="#ff5247" stroke-width="2.4"/>
        <circle cx="150" cy="150" r="2.5" fill="#39ff7a"/>
      </svg>
      <div class="sweepwrap"><div class="sweep"></div></div>
    </div>
    <div>
      <div class="grow">
        <div class="kpi" data-anim style="--d:2"><div class="n" data-count="100">0<span class="u">%</span></div><div class="l">RECALL · validación</div></div>
        <div class="kpi" data-anim style="--d:3"><div class="n" data-count="8">0</div><div class="l">HALLAZGOS REALES</div></div>
      </div>
      <ul class="pts" style="margin-top:2.4vh">
        <li data-anim style="--d:4">12 anomalías inyectadas para medir → <b class="hot">todas detectadas</b>.</li>
        <li data-anim style="--d:5">+ 8 vuelos reales genuinamente anómalos en el top-12.</li>
        <li data-anim style="--d:6">Corrida en <b>clúster QEMU</b> (nodo1 + nodo2, 4 lotes c/u).</li>
      </ul>
    </div>
  </div>
</section>

<!-- 9 ANALISIS -->
<section class="slide" data-rubric="Análisis crítico · 10%" data-notes="Analisis honesto: escala bien, pero la eficiencia baja por overhead de coordinacion. La leccion clave es la granularidad: la carga densa acelera; la variante con datos reales de bajo volumen es I/O-bound y NO acelera (speedup<1). No es un fallo, es la leccion. Y demostramos tolerancia a fallos.">
  <h2 class="t" data-anim style="--d:0">Análisis crítico</h2>
  <ul class="pts">
    <li data-anim style="--d:1"><b>Escala bien</b> (S₈=5,59); la eficiencia baja a 0,70 por el <b>overhead de coordinación</b> creciente.</li>
    <li data-anim style="--d:2"><b class="amber">Granularidad = variable clave</b>: la carga densa acelera; la variante con <b>datos reales</b> (636 vuelos) es <b>I/O-bound</b> y <span class="amber">no acelera</span> (Sₚ&lt;1).</li>
    <li data-anim style="--d:3">No es un fallo → es la <b>lección de granularidad</b>, reportada con honestidad.</li>
    <li data-anim style="--d:4"><b>Tolerancia a fallos demostrada</b>: con un nodo caído, el job igual completó 8/8.</li>
  </ul>
</section>

<!-- 10 SISTEMA EN VIVO -->
<section class="slide" data-rubric="Sistema real · demo" data-notes="Mostrar el sistema real funcionando: a la izquierda el dashboard de la TUI (torre de control, mini-radar, sectores, alertas); a la derecha la curva de speedup generada por el benchmark. Todo es evidencia real y trazable. Ofrecer demo en vivo.">
  <h2 class="t" data-anim style="--d:0">El sistema, en vivo</h2>
  <div class="cols">
    <div data-anim style="--d:1"><div class="foto">__TUI_SVG__</div><div class="cap">Dashboard TUI · torre de control (captura real)</div></div>
    <div data-anim style="--d:2"><div class="foto"><img src="__SPEEDUP_PNG__" alt="speedup"></div><div class="cap">Gráfico de speedup generado por el benchmark</div></div>
  </div>
</section>

<!-- 11 CONCLUSIONES -->
<section class="slide center" data-rubric="Conclusiones" data-notes="Cerrar: un orquestador distribuido propio detecta y rankea anomalias ADS-B con evidencia reproducible; speedup 5.59 y equivalencia justifican distribuir; recall 1.0; la granularidad decide. Trabajo futuro: Dask, kernels OpenMP, Isolation Forest. Ofrecer demo en vivo. Gracias.">
  <h2 class="t" data-anim style="--d:0">Conclusiones</h2>
  <ul class="pts" style="max-width:70ch">
    <li data-anim style="--d:1">Un <b>orquestador distribuido propio</b> detecta y rankea anomalías ADS-B con <b>evidencia reproducible</b>.</li>
    <li data-anim style="--d:2"><b class="hot">Speedup 5,59×</b> (E₈=0,70) + <b>equivalencia</b> exacta → distribuir se justifica.</li>
    <li data-anim style="--d:3"><b>Recall 1,0</b>: la calidad se mantiene. La <b>granularidad</b> decide si conviene.</li>
    <li data-anim style="--d:4"><b>Trabajo futuro</b>: escalar a datos masivos, Dask + kernels OpenMP, Isolation Forest.</li>
  </ul>
  <div class="grow" data-anim style="--d:5"><span class="cap" style="font-size:14px;color:var(--phos)">¡Gracias! · demo en vivo disponible (TUI → radar HTML)</span></div>
</section>

</div>

<script>
const slides=[...document.querySelectorAll('.slide')];
const bar=document.getElementById('bar'), cur=document.getElementById('cur'), tot=document.getElementById('tot');
let i=0; tot.textContent=slides.length;

function rubric(s){
  const old=s.querySelector('.rubric'); if(old) old.remove();
  const r=s.dataset.rubric; if(!r) return;
  const d=document.createElement('div'); d.className='rubric'+(r.includes('20%')||r.includes('Arquitectura')?'':' dim'); d.textContent=r;
  s.appendChild(d);
}
slides.forEach(rubric);

function show(n){
  i=Math.max(0,Math.min(slides.length-1,n));
  slides.forEach((s,k)=>s.classList.toggle('active',k===i));
  bar.style.width=((i+1)/slides.length*100)+'%';
  cur.textContent=i+1;
  // count-up de KPIs de la diapositiva activa
  slides[i].querySelectorAll('[data-count]').forEach(el=>{
    const to=parseFloat(el.dataset.count), dec=(to%1!==0)?2:0, suf=el.querySelector('.u')?el.querySelector('.u').outerHTML:'';
    let t0=null; function step(ts){if(t0==null)t0=ts;const k=Math.min(1,(ts-t0)/900);const e=1-Math.pow(1-k,3);
      el.innerHTML=(to*e).toFixed(dec)+suf; if(k<1)requestAnimationFrame(step);} requestAnimationFrame(step);
  });
}
function next(){show(i+1)} function prev(){show(i-1)}
document.addEventListener('keydown',e=>{
  if(e.key==='ArrowRight'||e.key===' '||e.key==='ArrowDown'||e.key==='PageDown'){e.preventDefault();next();}
  else if(e.key==='ArrowLeft'||e.key==='ArrowUp'||e.key==='PageUp'){e.preventDefault();prev();}
  else if(e.key==='Home'){show(0);} else if(e.key==='End'){show(slides.length-1);}
  else if(e.key==='f'||e.key==='F'){if(!document.fullscreenElement)document.documentElement.requestFullscreen&&document.documentElement.requestFullscreen();else document.exitFullscreen&&document.exitFullscreen();}
});
document.getElementById('deck').addEventListener('click',e=>{ if(e.clientX < innerWidth*0.28) prev(); else next(); });
show(0);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
