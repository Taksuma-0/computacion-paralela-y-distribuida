#!/usr/bin/env python3
"""Generador del reporte HTML de la tarea ADS-B (task_adsb).

Lee el `record` de un job (el mismo dict que el coordinador escribe en
results/<job_id>.json, bajo la clave "result" va la salida de merge()) y produce
un HTML autocontenido y animado: un SCOPE de radar de control aereo donde se
dibujan las trayectorias mas anomalas, con barrido, datablocks y flight strips.

Sin dependencias: un unico .html con CSS+JS inline (abre offline con doble clic).

Uso:
    # programatico (lo llama la TUI desde el record en memoria):
    import adsb_report; adsb_report.build_html(record, "results/<job_id>.html")

    # standalone (desde la evidencia ya escrita):
    python adsb_report.py results/<job_id>.json [--out results/<job_id>.html]
"""

import argparse
import json
import os
import sys


def _bbox(paths):
    """Caja lat/lon comun a todas las trayectorias (para encuadrar el scope)."""
    lats, lons = [], []
    for p in paths:
        for pt in p:
            lats.append(pt[0])
            lons.append(pt[1])
    if not lats:  # fallback: Sudamerica
        return {"min_lat": -35.0, "max_lat": 6.0, "min_lon": -78.0, "max_lon": -45.0}
    return {"min_lat": min(lats), "max_lat": max(lats),
            "min_lon": min(lons), "max_lon": max(lons)}


def _prepare_data(record):
    res = record.get("result") or {}
    top_k = res.get("top_k", []) or []
    examples = res.get("examples_by_type", {}) or {}
    paths = [t["path"] for t in top_k if t.get("path")]
    paths += [t["path"] for t in examples.values() if t.get("path")]
    return {
        "meta": {
            "job_id": record.get("job_id"),
            "task_name": record.get("task_name"),
            "workers": record.get("workers", []),
            "healthy_workers": record.get("healthy_workers", []),
            "n_chunks": record.get("n_chunks"),
            "completed": record.get("completed"),
            "elapsed": record.get("elapsed"),
            "elapsed_baseline": record.get("elapsed_baseline"),
            "speedup": record.get("speedup"),
            "coordinator_location": record.get("coordinator_location"),
            "payload": record.get("payload", {}),
            "timestamp": record.get("timestamp"),
        },
        "per_worker": record.get("per_worker", {}),
        "per_chunk": [{"chunk_id": c.get("chunk_id"), "worker": c.get("worker"),
                       "seconds": c.get("seconds")} for c in record.get("per_chunk", [])],
        "result": {
            "n_traj": res.get("n_traj"), "n_injected": res.get("n_injected"),
            "n_normal": res.get("n_normal"),
            "detected_injected_in_topk": res.get("detected_injected_in_topk"),
            "precision_at_k": res.get("precision_at_k"), "recall": res.get("recall"),
            "false_positive_rate": res.get("false_positive_rate"),
            "precision_threshold": res.get("precision_threshold"),
            "tp": res.get("tp"), "fp": res.get("fp"),
            "z_threshold": res.get("z_threshold"), "k": res.get("k"),
            "top_k": top_k, "examples_by_type": examples,
        },
        "bbox": _bbox(paths),
    }


def build_html(record, out_path):
    data = _prepare_data(record)
    html = PLANTILLA_HTML.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False, allow_nan=False))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


PLANTILLA_HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ADS-B ANOMALY SCOPE</title>
<style>
:root{
  --void:#04100a; --panel:#06170e; --panel2:#08200f; --grid:#114026; --grid2:#0c2c1b;
  --phos:#39ff7a; --phos-dim:#1f8f4d; --ink:#bfe9cf; --ink-dim:#5f8a72; --paper:#e9fbef;
  --rodeo:#3fd0ff; --holding:#ffb000; --descenso_anomalo:#ff5247; --go_around:#c77dff;
  --warn:#ffb000; --bad:#ff5247;
  --mono:ui-monospace,"Cascadia Code","SFMono-Regular","Consolas","Liberation Mono",monospace;
}
*{box-sizing:border-box}
html,body{margin:0}
body{
  background:
    radial-gradient(1200px 700px at 30% -10%, #0a2417 0%, var(--void) 60%),
    var(--void);
  color:var(--ink); font-family:var(--mono); font-size:14px; line-height:1.45;
  padding:18px; letter-spacing:.02em;
  -webkit-font-smoothing:antialiased;
}
.scanlines{position:fixed;inset:0;pointer-events:none;z-index:50;opacity:.35;
  background:repeating-linear-gradient(0deg,rgba(0,0,0,0) 0 2px,rgba(0,0,0,.18) 2px 3px)}
.wrap{max-width:1180px;margin:0 auto;position:relative;z-index:1}

/* ---- status bar ---- */
.status{border:1px solid var(--grid);background:linear-gradient(180deg,var(--panel2),var(--panel));
  border-radius:10px;padding:12px 16px;margin-bottom:14px}
.status .top{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.brand{font-size:20px;font-weight:700;letter-spacing:.18em;color:var(--paper);
  text-shadow:0 0 12px rgba(57,255,122,.45)}
.brand .dot{color:var(--phos);animation:blink 1.4s steps(1) infinite}
.tag{color:var(--ink-dim);font-size:11px;letter-spacing:.16em}
.readout{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}
.cell{border:1px solid var(--grid2);border-radius:6px;padding:5px 10px;font-size:11px;
  letter-spacing:.1em;color:var(--ink-dim);background:rgba(8,32,18,.5)}
.cell b{color:var(--paper);font-weight:700;letter-spacing:.04em}
.cell.alert b{color:var(--phos)}

/* ---- main grid ---- */
.deck{display:grid;grid-template-columns:minmax(0,1.25fr) minmax(280px,.85fr);gap:14px}
@media(max-width:900px){.deck{grid-template-columns:1fr}}
.frame{border:1px solid var(--grid);background:linear-gradient(180deg,var(--panel2),var(--panel));
  border-radius:12px;padding:14px;position:relative;overflow:hidden}
.frame > h2{margin:0 0 10px;font-size:12px;letter-spacing:.22em;color:var(--ink-dim);font-weight:700;
  display:flex;justify-content:space-between;align-items:center}
.frame > h2 .hint{color:var(--phos-dim);font-weight:400;letter-spacing:.08em}

/* ---- scope ---- */
.scope-stage{position:relative;width:100%;max-width:560px;margin:0 auto;aspect-ratio:1/1}
.scope-stage svg{position:absolute;inset:0;width:100%;height:100%}
.sweep{position:absolute;inset:0;border-radius:50%;pointer-events:none;mix-blend-mode:screen;
  background:conic-gradient(from var(--a,0deg),
    rgba(57,255,122,0) 0deg, rgba(57,255,122,0) 250deg,
    rgba(57,255,122,.04) 320deg, rgba(57,255,122,.12) 356deg,
    rgba(120,255,180,.5) 359.3deg, rgba(57,255,122,0) 360deg);
  animation:sweep 4.6s linear infinite}
ring{}
.ring{fill:none;stroke:var(--grid2);stroke-width:1}
.ring.r-out{stroke:var(--grid)}
.cross{stroke:var(--grid2);stroke-width:1}
.az{fill:var(--ink-dim);font-size:9px;letter-spacing:.1em}
.rng{fill:var(--phos-dim);font-size:8px;opacity:.7}
.track{fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;opacity:.92;
  filter:drop-shadow(0 0 4px currentColor)}
.track.dim{opacity:.18;filter:none}
.halo{fill:none;stroke-width:1.5;opacity:.9}
.plane{}
.db{font-size:9px;letter-spacing:.04em;fill:var(--paper)}
.db rect{}
.center{fill:var(--phos)}

/* ---- flight strips ---- */
.strips{display:flex;flex-direction:column;gap:7px;max-height:560px;overflow:auto}
.strip{display:grid;grid-template-columns:22px 1fr auto;gap:9px;align-items:center;
  border:1px solid var(--grid2);border-left-width:4px;border-radius:6px;padding:7px 9px;
  background:rgba(6,23,14,.7);cursor:pointer;transition:transform .1s,background .15s,border-color .15s}
.strip:hover,.strip.sel{background:rgba(14,52,32,.7);transform:translateX(-2px)}
.strip .rank{color:var(--ink-dim);font-size:11px;text-align:right}
.strip .cs{color:var(--paper);font-weight:700;letter-spacing:.06em}
.strip .meta{color:var(--ink-dim);font-size:10px;letter-spacing:.08em;margin-top:1px}
.strip .sc{text-align:right}
.strip .sc b{color:var(--paper);font-size:15px}
.strip .sc .z{color:var(--ink-dim);font-size:9px;letter-spacing:.1em}
.kind{display:inline-block;font-size:9px;letter-spacing:.12em;padding:1px 6px;border-radius:4px;
  border:1px solid currentColor}
.bar{height:3px;border-radius:2px;background:var(--grid2);margin-top:6px;overflow:hidden}
.bar > i{display:block;height:100%;width:0;border-radius:2px;background:currentColor;
  transition:width 1.1s cubic-bezier(.2,.7,.2,1)}

/* ---- metrics ---- */
.gauges{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:14px}
@media(max-width:760px){.gauges{grid-template-columns:repeat(2,1fr)}}
.gauge{border:1px solid var(--grid);background:linear-gradient(180deg,var(--panel2),var(--panel));
  border-radius:10px;padding:14px}
.gauge .lab{font-size:10px;letter-spacing:.16em;color:var(--ink-dim)}
.gauge .val{font-size:30px;font-weight:700;color:var(--paper);margin-top:6px;line-height:1;
  text-shadow:0 0 14px rgba(57,255,122,.35)}
.gauge .val .u{font-size:14px;color:var(--phos-dim);margin-left:2px}
.gauge .sub{font-size:10px;color:var(--ink-dim);margin-top:5px;letter-spacing:.06em}
.gauge.good .val{color:var(--phos)}
.gauge.warn .val{color:var(--warn)}

/* ---- patterns + dist ---- */
.lower{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(260px,1fr);gap:14px;margin-top:14px}
@media(max-width:900px){.lower{grid-template-columns:1fr}}
.pats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
@media(max-width:620px){.pats{grid-template-columns:repeat(2,1fr)}}
.pat{border:1px solid var(--grid2);border-radius:8px;padding:8px;background:rgba(6,23,14,.6);text-align:center}
.pat svg{width:100%;height:96px;display:block}
.pat .pk{font-size:10px;letter-spacing:.12em;font-weight:700;margin-top:4px}
.pat .pm{font-size:9px;color:var(--ink-dim);letter-spacing:.06em}
.dist .row{display:grid;grid-template-columns:74px 1fr 40px;gap:8px;align-items:center;margin-bottom:9px}
.dist .wn{color:var(--paper);font-size:11px;letter-spacing:.06em}
.dist .track2{height:14px;background:var(--grid2);border-radius:4px;overflow:hidden}
.dist .track2 > i{display:block;height:100%;width:0;background:linear-gradient(90deg,var(--phos-dim),var(--phos));
  transition:width 1s ease-out}
.dist .cn{color:var(--ink-dim);font-size:11px;text-align:right}
.spark{display:flex;align-items:flex-end;gap:1px;height:34px;margin-top:6px}
.spark > i{flex:1;background:var(--phos-dim);border-radius:1px 1px 0 0;min-height:1px;opacity:.8}

.foot{color:var(--ink-dim);font-size:10px;letter-spacing:.1em;text-align:center;margin-top:18px;
  border-top:1px solid var(--grid2);padding-top:12px}
.foot b{color:var(--phos-dim)}

@keyframes sweep{to{--a:360deg}}
@property --a{syntax:'<angle>';inherits:false;initial-value:0deg}
@keyframes blink{50%{opacity:.25}}
@keyframes pulse{0%,100%{r:3;opacity:1}50%{r:11;opacity:.15}}
@media(prefers-reduced-motion:reduce){
  .sweep{animation:none;opacity:.18}
  .brand .dot{animation:none}
  .track{stroke-dasharray:none!important;stroke-dashoffset:0!important}
}
</style>
</head>
<body>
<div class="scanlines"></div>
<div class="wrap">

  <header class="status">
    <div class="top">
      <span class="brand">ADS-B ANOMALY SCOPE<span class="dot">_</span></span>
      <span class="tag" id="tag-sector">SECTOR SUDAMÉRICA · DETECCIÓN DISTRIBUIDA NO SUPERVISADA</span>
    </div>
    <div class="readout" id="readout"></div>
  </header>

  <div class="deck">
    <section class="frame">
      <h2>RADAR · TOP CONTACTOS ANÓMALOS <span class="hint" id="scope-hint">barrido activo</span></h2>
      <div class="scope-stage">
        <svg id="scope" viewBox="0 0 600 600" aria-label="scope de radar"></svg>
        <div class="sweep" aria-hidden="true"></div>
      </div>
    </section>

    <aside class="frame">
      <h2>FLIGHT STRIPS · RANKING <span class="hint">hover = fijar contacto</span></h2>
      <div class="strips" id="strips"></div>
    </aside>
  </div>

  <div class="gauges" id="gauges"></div>

  <div class="lower">
    <section class="frame">
      <h2>PATRONES DE MANIOBRA DETECTADOS <span class="hint">un ejemplo por tipo</span></h2>
      <div class="pats" id="pats"></div>
    </section>
    <section class="frame dist">
      <h2>CÓMPUTO DISTRIBUIDO <span class="hint">reparto de chunks</span></h2>
      <div id="dist"></div>
      <div style="font-size:10px;letter-spacing:.12em;color:var(--ink-dim);margin-top:10px">
        TIEMPO POR CHUNK</div>
      <div class="spark" id="spark"></div>
    </section>
  </div>

  <p class="foot">Generado por <b>adsb_report.py</b> · tarea <b>task_adsb</b> sobre el orquestador
     distribuido (QEMU) · scoring z-robusto (MAD) · evidencia <b id="foot-job"></b></p>
</div>

<script>
const DATA = __DATA_JSON__;
const M = DATA.meta, R = DATA.result;
const TYPE_COLOR = {rodeo:'#3fd0ff', holding:'#ffb000', descenso_anomalo:'#ff5247', go_around:'#c77dff', normal:'#39ff7a'};
const TYPE_NAME  = {rodeo:'RODEO', holding:'HOLDING', descenso_anomalo:'DESCENSO', go_around:'GO-AROUND'};
const REASON     = {len_ratio:'desvío de ruta', turn_sum:'curvatura', vrate_max:'tasa vertical'};
const reduce = matchMedia('(prefers-reduced-motion:reduce)').matches;
const SVGNS = 'http://www.w3.org/2000/svg';
const el = (n,a={})=>{const e=document.createElementNS(SVGNS,n);for(const k in a)e.setAttribute(k,a[k]);return e;};
const pct = v => (v==null?'—':(v*100).toFixed(v>=0.999?0:1));
const colOf = t => TYPE_COLOR[t&&t.atype] || TYPE_COLOR.normal;

/* ---------- status readout ---------- */
(function(){
  const nodes = (M.healthy_workers&&M.healthy_workers.length?M.healthy_workers:(M.workers||[]).map(w=>w.name)).join(' · ')||'—';
  const cells = [
    ['CONTACTOS', (R.n_traj||0).toLocaleString('es')],
    ['INYECTADAS', R.n_injected||0],
    ['NODOS', nodes],
    ['CHUNKS', (M.completed||0)+'/'+(M.n_chunks||0)],
    ['T', (M.elapsed!=null?M.elapsed+'s':'—')],
    ['JOB', M.job_id||'—'],
  ];
  document.getElementById('readout').innerHTML = cells.map(c=>
    `<span class="cell alert">${c[0]} <b>${c[1]}</b></span>`).join('');
  document.getElementById('foot-job').textContent = M.job_id||'';
})();

/* ---------- proyección geográfica al scope ---------- */
const CX=300, CY=300, RAD=270;
function proj(lat, lon){
  const b=DATA.bbox;
  const mlat=(b.min_lat+b.max_lat)/2, mlon=(b.min_lon+b.max_lon)/2;
  const span=Math.max(b.max_lat-b.min_lat, b.max_lon-b.min_lon, 0.01);
  const sc=(RAD*1.62)/span;
  return [CX+(lon-mlon)*sc, CY-(lat-mlat)*sc];
}
const dOf = path => path.map((p,i)=>{const xy=proj(p[0],p[1]);return (i?'L':'M')+xy[0].toFixed(1)+' '+xy[1].toFixed(1);}).join(' ');
function farthestIdx(path){ // waypoint mas lejos de la recta origen-destino (la maniobra)
  const a=proj(path[0][0],path[0][1]), b=proj(path[path.length-1][0],path[path.length-1][1]);
  let bi=0,bd=-1; const L=Math.hypot(b[0]-a[0],b[1]-a[1])||1;
  for(let i=1;i<path.length-1;i++){const p=proj(path[i][0],path[i][1]);
    const d=Math.abs((b[1]-a[1])*p[0]-(b[0]-a[0])*p[1]+b[0]*a[1]-b[1]*a[0])/L;
    if(d>bd){bd=d;bi=i;}}
  return bi;
}

/* ---------- construir el scope ---------- */
const scope = document.getElementById('scope');
function gridScope(){
  const g=el('g');
  [RAD,RAD*0.72,RAD*0.46,RAD*0.2].forEach((r,i)=>{
    g.appendChild(el('circle',{class:'ring'+(i===0?' r-out':''),cx:CX,cy:CY,r}));});
  g.appendChild(el('line',{class:'cross',x1:CX-RAD,y1:CY,x2:CX+RAD,y2:CY}));
  g.appendChild(el('line',{class:'cross',x1:CX,y1:CY-RAD,x2:CX,y2:CY+RAD}));
  for(let a=0;a<360;a+=30){
    const rad=(a-90)*Math.PI/180, x=CX+Math.cos(rad)*(RAD+12), y=CY+Math.sin(rad)*(RAD+12);
    const t=el('text',{class:'az',x,y,'text-anchor':'middle','dominant-baseline':'middle'});
    t.textContent=String(a).padStart(3,'0'); g.appendChild(t);
  }
  g.appendChild(el('circle',{class:'center',cx:CX,cy:CY,r:2.5}));
  scope.appendChild(g);
}
gridScope();

const planes=[]; // {pathEl,len,plane,dir,color}
const trackById={};
function drawTracks(){
  const clip=el('clipPath',{id:'scopeclip'}); clip.appendChild(el('circle',{cx:CX,cy:CY,r:RAD-2}));
  scope.appendChild(clip);
  const layer=el('g',{'clip-path':'url(#scopeclip)'}); scope.appendChild(layer);
  const maxScore=Math.max(...R.top_k.map(t=>t.score),1);
  R.top_k.forEach((t,i)=>{
    const color=colOf(t), d=dOf(t.path);
    const pth=el('path',{class:'track',d,stroke:color,'data-id':t.id});
    layer.appendChild(pth);
    // halo en la maniobra
    const fp=proj(...[t.path[farthestIdx(t.path)][0],t.path[farthestIdx(t.path)][1]]);
    const halo=el('circle',{class:'halo',cx:fp[0],cy:fp[1],r:3,stroke:color});
    if(!reduce) halo.style.animation=`pulse ${1.6+ (i%4)*0.25}s ease-in-out ${i*0.12}s infinite`;
    layer.appendChild(halo);
    // avion (triangulo apuntando a +x)
    const plane=el('polygon',{class:'plane',points:'9,0 -6,5 -6,-5',fill:color,
      stroke:'#04100a','stroke-width':'.6'});
    layer.appendChild(plane);
    // datablock (oculto; aparece al seleccionar)
    const db=el('g',{class:'db','data-db':t.id,opacity:0});
    const txt=el('text',{x:0,y:0});
    txt.textContent=`#${i+1} ${t.route} ${TYPE_NAME[t.atype]||''} z${Math.round(t.score)}`;
    db.appendChild(txt); layer.appendChild(db);
    const L=pth.getTotalLength();
    if(!reduce){pth.style.strokeDasharray=L;pth.style.strokeDashoffset=L;}
    planes.push({pth,L,plane,db,txt,color,len:t.path.length});
    trackById[t.id]={pth,db,plane,halo};
  });
}
drawTracks();

/* ---------- animación: trazado en cascada + aviones recorriendo ---------- */
function revealAndFly(){
  planes.forEach((o,i)=>{
    if(!reduce){
      o.pth.animate([{strokeDashoffset:o.L},{strokeDashoffset:0}],
        {duration:1100,delay:i*150,easing:'cubic-bezier(.2,.7,.2,1)',fill:'forwards'});
    }
  });
  let t0=null;
  function frame(ts){
    if(t0==null)t0=ts;
    const base=(ts-t0)/5200; // periodo de vuelo
    planes.forEach((o,i)=>{
      const u=((base+i/planes.length)%1);
      const pt=o.pth.getPointAtLength(u*o.L);
      const pt2=o.pth.getPointAtLength(Math.min(o.L,u*o.L+1));
      const ang=Math.atan2(pt2.y-pt.y,pt2.x-pt.x)*180/Math.PI;
      o.plane.setAttribute('transform',`translate(${pt.x.toFixed(1)},${pt.y.toFixed(1)}) rotate(${ang.toFixed(0)})`);
      if(+o.db.getAttribute('opacity')>0) o.db.setAttribute('transform',`translate(${(pt.x+10).toFixed(1)},${(pt.y-8).toFixed(1)})`);
    });
    requestAnimationFrame(frame);
  }
  if(!reduce) requestAnimationFrame(frame);
  else planes.forEach(o=>{const pt=o.pth.getPointAtLength(o.L*0.5);
    o.plane.setAttribute('transform',`translate(${pt.x},${pt.y})`);});
}
revealAndFly();

/* ---------- flight strips ---------- */
const stripsEl=document.getElementById('strips');
const maxScore=Math.max(...R.top_k.map(t=>t.score),1);
R.top_k.forEach((t,i)=>{
  const color=colOf(t);
  const s=document.createElement('div');
  s.className='strip'; s.style.borderLeftColor=color; s.dataset.id=t.id;
  s.innerHTML=`
    <div class="rank">${String(i+1).padStart(2,'0')}</div>
    <div>
      <div class="cs">${t.route} <span class="kind" style="color:${color}">${TYPE_NAME[t.atype]||'—'}</span></div>
      <div class="meta">ICAO ${String(t.id).padStart(5,'0')} · ${REASON[t.reason]||t.reason} · ${t.injected?'GROUND-TRUTH ✓':'—'}</div>
      <div class="bar" style="color:${color}"><i data-w="${(t.score/maxScore*100).toFixed(1)}"></i></div>
    </div>
    <div class="sc"><b>${Math.round(t.score)}</b><div class="z">σ-ROB</div></div>`;
  const hi=on=>{ for(const id in trackById){const o=trackById[id];
      o.pth.classList.toggle('dim', on && +id!==t.id);}
    const o=trackById[t.id]; if(o){o.db.setAttribute('opacity',on?1:0);}
    s.classList.toggle('sel',on);};
  s.addEventListener('mouseenter',()=>hi(true));
  s.addEventListener('mouseleave',()=>hi(false));
  stripsEl.appendChild(s);
});
requestAnimationFrame(()=>document.querySelectorAll('.bar > i').forEach(b=>b.style.width=b.dataset.w+'%'));

/* ---------- gauges (count-up) ---------- */
function gauge(lab,val,cls,sub){return `<div class="gauge ${cls}"><div class="lab">${lab}</div>
  <div class="val" data-to="${val.to}" data-dec="${val.dec||0}" data-suf="${val.suf||''}">0${val.suf||''}</div>
  <div class="sub">${sub}</div></div>`;}
document.getElementById('gauges').innerHTML=[
  gauge('PRECISION@'+R.k,{to:(R.precision_at_k||0)*100,suf:'%'},'good','top-k que son anomalías reales'),
  gauge('RECALL',{to:(R.recall||0)*100,suf:'%'},'good','anomalías detectadas (umbral σ≥'+R.z_threshold+')'),
  gauge('FALSOS POS.',{to:(R.false_positive_rate||0)*100,dec:2,suf:'%'},((R.false_positive_rate||0)<0.02?'good':'warn'),'normales marcadas por error'),
  gauge('SPEEDUP',{to:M.speedup||0,dec:2,suf:'×'},((M.speedup||0)>=1?'good':'warn'),(M.elapsed||'?')+'s vs '+(M.elapsed_baseline||'?')+'s base'),
  gauge('TP / FP',{to:R.tp||0},'','vs '+(R.fp||0)+' falsos · σ-robusto'),
].join('');
document.querySelectorAll('.gauge .val').forEach(v=>{
  const to=+v.dataset.to, dec=+v.dataset.dec, suf=v.dataset.suf;
  if(reduce){v.innerHTML=to.toFixed(dec)+`<span class="u">${suf}</span>`;return;}
  let t0=null; const dur=1000;
  function step(ts){if(t0==null)t0=ts;const k=Math.min(1,(ts-t0)/dur);const e=1-Math.pow(1-k,3);
    v.innerHTML=(to*e).toFixed(dec)+`<span class="u">${suf}</span>`;if(k<1)requestAnimationFrame(step);}
  requestAnimationFrame(step);
});

/* ---------- mini-scopes por patrón ---------- */
const patsEl=document.getElementById('pats');
['rodeo','holding','descenso_anomalo','go_around'].forEach(tp=>{
  const t=R.examples_by_type[tp]; const color=TYPE_COLOR[tp];
  const div=document.createElement('div'); div.className='pat';
  if(!t){div.innerHTML=`<div style="height:96px;display:flex;align-items:center;justify-content:center;color:var(--ink-dim);font-size:10px">SIN MUESTRA</div>
    <div class="pk" style="color:${color}">${TYPE_NAME[tp]}</div>`;patsEl.appendChild(div);return;}
  // mini svg con bbox propio del path
  const lats=t.path.map(p=>p[0]),lons=t.path.map(p=>p[1]);
  const mnla=Math.min(...lats),mxla=Math.max(...lats),mnlo=Math.min(...lons),mxlo=Math.max(...lons);
  const span=Math.max(mxla-mnla,mxlo-mnlo,0.01), s=70/span;
  const d=t.path.map((p,i)=>{const x=50+(p[1]-(mnlo+mxlo)/2)*s,y=48-(p[0]-(mnla+mxla)/2)*s;
    return (i?'L':'M')+x.toFixed(1)+' '+y.toFixed(1);}).join(' ');
  const ns='http://www.w3.org/2000/svg';
  div.innerHTML=`<svg viewBox="0 0 100 96"><path d="${d}" fill="none" stroke="${color}" stroke-width="1.6"
      stroke-linejoin="round" stroke-linecap="round" style="filter:drop-shadow(0 0 3px ${color})"/></svg>
    <div class="pk" style="color:${color}">${TYPE_NAME[tp]}</div>
    <div class="pm">${t.route} · z${Math.round(t.score)} · ${REASON[t.reason]||t.reason}</div>`;
  // animar trazado
  const path=div.querySelector('path');
  if(!reduce){const L=path.getTotalLength();path.style.strokeDasharray=L;path.style.strokeDashoffset=L;
    path.animate([{strokeDashoffset:L},{strokeDashoffset:0}],{duration:1200,delay:300,fill:'forwards',easing:'ease-out'});}
  patsEl.appendChild(div);
});

/* ---------- distribución por worker + sparkline ---------- */
(function(){
  const pw=DATA.per_worker||{}; const names=Object.keys(pw);
  const maxc=Math.max(1,...names.map(n=>pw[n].chunks||0));
  document.getElementById('dist').innerHTML=names.map(n=>{
    const c=pw[n].chunks||0, sec=(pw[n].busy_seconds||0).toFixed(1);
    return `<div class="row"><div class="wn">${n}</div>
      <div class="track2"><i data-w="${(c/maxc*100).toFixed(0)}"></i></div>
      <div class="cn">${c} <span style="opacity:.6">· ${sec}s</span></div></div>`;}).join('')
    || '<div style="color:var(--ink-dim);font-size:11px">sin datos de workers</div>';
  requestAnimationFrame(()=>document.querySelectorAll('.dist .track2 > i').forEach(b=>b.style.width=b.dataset.w+'%'));
  const pc=DATA.per_chunk||[]; const mx=Math.max(1,...pc.map(c=>c.seconds||0));
  document.getElementById('spark').innerHTML=pc.map(c=>
    `<i style="height:${Math.max(4,(c.seconds||0)/mx*100)}%" title="chunk ${c.chunk_id}: ${c.seconds}s @${c.worker}"></i>`).join('');
})();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(description="Genera el HTML del reporte ADS-B desde results/<job_id>.json")
    ap.add_argument("record_json", help="ruta a results/<job_id>.json")
    ap.add_argument("--out", default=None, help="ruta de salida .html (por defecto, junto al JSON)")
    a = ap.parse_args()
    with open(a.record_json, encoding="utf-8") as f:
        record = json.load(f)
    out = a.out or os.path.splitext(a.record_json)[0] + ".html"
    build_html(record, out)
    print("HTML generado:", os.path.abspath(out))


if __name__ == "__main__":
    sys.exit(main())
