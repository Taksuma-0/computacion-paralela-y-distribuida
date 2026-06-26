# Guion de presentación — "El gato que aprende solo"
### Demo de cómputo distribuido con Ray (Computación Paralela y Distribuida · UTEM)

Duración objetivo: **8–10 min**. El guion está en bloques con (⏱ tiempo),
**[QUÉ DECIR]** y **[QUÉ MOSTRAR]**. Se apoya en las diapositivas del deck
*Ray distributed computing sobre QEMU* (se citan los slides relevantes).

> **Idea de una frase:** *"Tomamos el patrón del demo de primos (slide 12) y lo
> reemplazamos por una tarea de Machine Learning: en vez de repartir números,
> repartimos partidas; en vez de contar, el sistema aprende."*

---

## 1. Gancho (⏱ 0:30)

**[QUÉ DECIR]**
> "¿Y si una máquina aprende a jugar al gato **sola**, sin que le programemos
> ninguna estrategia? Y además, ¿qué pasa si la ponemos a aprender **más rápido**
> repartiendo el trabajo entre varios nodos? Eso es lo que hicimos con Ray sobre el
> clúster QEMU."

**[QUÉ MOSTRAR]** La interfaz `gato.html` abierta (sin jugar todavía).

---

## 2. Qué es: aprender por refuerzo (⏱ 1:30)

**[QUÉ DECIR]**
> "El agente empieza sabiendo **nada**: juega al azar. Lo ponemos a jugar **contra
> sí mismo** miles de veces (*self‑play*). Cada vez que una jugada termina en
> victoria, esa jugada se **refuerza** (+1); si termina en derrota, se **castiga**
> (−1); empate, neutro (0). Repetimos eso millones de veces y, sin decirle ninguna
> regla, el agente termina jugando bien. Es **aprendizaje por refuerzo** con el
> método de **Monte Carlo**."

> "La 'memoria' del agente es una tabla: para cada posición del tablero, qué tan
> buena resultó cada jugada. A eso se le llama la **política** o tabla Q."

**[QUÉ MOSTRAR]** La **curva de aprendizaje** del HTML; botón *Animar aprendizaje*.
Señala cómo el verde (no‑derrota) sube de ~60–75 % hasta ~99 %.

---

## 3. Por qué esto es un problema de cómputo distribuido (⏱ 1:30)

**[QUÉ DECIR]**
> "Aprender así requiere **muchísimas partidas**. Pero hay una propiedad clave:
> cada partida de self‑play es **independiente** de las demás. Eso lo hace
> *vergonzosamente paralelo*: podemos repartir las partidas entre muchos
> trabajadores que juegan al mismo tiempo, y después juntar lo aprendido."

> "Y este es **exactamente** el mismo patrón del demo de primos del laboratorio
> (slide 12): partir el trabajo, lanzar tareas remotas y agregar resultados. Solo
> cambiamos *qué* hace cada tarea."

**[QUÉ MOSTRAR]** Slides 4 y 6 del deck (driver/tasks/object refs; `refs =
[work.remote(x) ...]; ray.get(refs)`).

**[ANALOGÍA opcional]**
> "Es como un entrenador que manda a 8 alumnos a jugar 2.000 partidas cada uno.
> Vuelven, le cuentan qué les funcionó, y el entrenador actualiza el 'manual'.
> Al día siguiente reparte el manual mejorado y repiten. Cada 'día' es una
> **generación**."

---

## 4. Cómo se distribuye con Ray (⏱ 1:30)

**[QUÉ DECIR]**
> "En cada generación hacemos cuatro pasos, que son el patrón **map‑reduce** de Ray:"
>
> 1. **`ray.put(política)`** — publicamos la política actual en el *object store*;
>    así todos los trabajadores la reciben de forma eficiente (broadcast).
> 2. **`tarea.remote(...)`** — lanzamos K tareas en paralelo; cada una juega sus
>    partidas de self‑play. Ray decide en qué nodo corre cada una.
> 3. **`ray.get(refs)`** — recolectamos los resultados (aquí se materializa el
>    cómputo; es el único punto que bloquea).
> 4. **reduce** — fusionamos las estadísticas y actualizamos la política.
>
> "Repetimos por varias generaciones. Cada tarea reporta además **en qué nodo se
> ejecutó**, así que podemos ver la distribución real."

**[QUÉ MOSTRAR]** El código `gato_rl_ray.py` en la sección del driver (las 4 líneas
`ray.put / .remote / ray.get / fusionar`) y, si está vivo, el **Dashboard** (slide 8)
con las tareas y los nodos.

---

## 5. Demo en vivo (⏱ 2:30)

> **Plan A (con clúster):** mostrar el entrenamiento real en ray0.
> **Plan B (a prueba de fallos):** tener `gato.html` **ya generado** y mostrarlo.
> *Recomendación: ten listo el Plan B siempre; el aprendizaje ya está capturado en el HTML.*

**[QUÉ MOSTRAR / PASOS]**
1. En ray0 ya con Ray iniciado:
   ```bash
   cd ~/ray-demo && python gato_rl_ray.py 30 2000 8
   ```
   Señala la columna **no‑derrota subiendo** y la columna **nodos**.
2. Abre el **Dashboard** (http://127.0.0.1:8265) → pestaña *Jobs/Tasks*: "aquí se ven
   las tareas ejecutándose en paralelo".
3. Abre `gato.html`:
   - **Juega una partida** contra la IA en vivo (deja que el público sugiera jugadas;
     casi siempre **empata o gana** la IA → "nadie le programó esto, lo aprendió").
   - **Anima la curva** de aprendizaje.
   - Mueve el **deslizador del replay**: "en la generación 0 juega torpe; al final,
     juega como un experto. Esto es el mismo agente, distintas etapas del aprendizaje."

---

## 6. Rendimiento: speedup, eficiencia y overhead (⏱ 1:00)

**[QUÉ DECIR]**
> "Como buen laboratorio de cómputo paralelo, **medimos**, no solo ejecutamos
> (slide 17). Con `--benchmark` corremos el mismo total de partidas con 1 tarea y
> con K tareas, y calculamos: **Speedup S = T1/Tp**, **Eficiencia E = S/p** y
> **Overhead O = p·Tp − T1** (slide 16)."

> "Hay un detalle clave de **granularidad**: si las tareas son muy chicas, el costo
> de coordinar/serializar domina y no aceleramos. Por eso subimos las partidas por
> tarea: tareas con suficiente cómputo amortizan el overhead. Si una tarea hiciera
> 5 partidas, Ray pierde más tiempo coordinando que jugando."

**[QUÉ MOSTRAR]** Los números de `--benchmark` (o los chips del HTML si incluiste
speedup) y el slide 16.

---

## 7. Cierre: ¿cuándo conviene Ray? (⏱ 0:30)

**[QUÉ DECIR]**
> "Ray brilla justo en esto: **código Python arbitrario** (no big‑data tabular),
> con tareas heterogéneas y necesidad de observar la ejecución (slide 19). Nuestro
> agente de RL encaja perfecto. Y lo importante: Ray **no reemplaza el razonamiento
> paralelo**, lo hace **programable y observable** desde Python (slide 20)."

> "Resumen: pasamos del demo que **cuenta** primos a uno que **aprende**, usando el
> mismo patrón distribuido. Misma infraestructura, una tarea con mucho más sabor a
> ciencia de datos."

---

## 8. Preguntas probables (y cómo responder)

**¿Por qué Monte Carlo y no una red neuronal (DQN)?**
> Porque el gato es chico (~4.500 estados): una tabla basta y converge rápido. Una
> red necesitaría PyTorch/TensorFlow, que no están en la VM Debian minimal. Mantuvimos
> todo en librería estándar para que corra tal cual en el clúster.

**¿La IA juega perfecto?**
> Aprende a jugar muy bien por self‑play (no pierde casi nunca), pero no es minimax
> exhaustivo: optimiza contra su propia distribución de juego. Un humano muy fino
> podría encontrar una grieta — y eso mismo es un buen punto: MC aprende de
> experiencia, no calcula todo el árbol. (En la interfaz hay una pequeña red de
> seguridad táctica para no regalar partidas en posiciones raras.)

**¿Dónde está el paralelismo exactamente?**
> En los *rollouts*: las K tareas `@ray.remote` que juegan partidas a la vez. La
> agregación (reduce) y la actualización de la política las hace el driver.

**¿Cómo se vería en multinodo?**
> El código no cambia: ya reparte tareas y reporta hostnames. Con red interna VM↔VM,
> la columna *nodos* y los chips mostrarían `ray0, ray1, ray2`.

**¿Por qué la curva a veces baja un poquito?**
> Es estocástico: la evaluación usa un rival aleatorio y un número finito de partidas;
> hay ruido. La tendencia general es lo que importa.

**¿Cuánto tarda?**
> El cómputo en sí son segundos para esta escala; el grueso del tiempo de un
> laboratorio es **levantar el runtime** y **enviar el job** — por eso medimos solo
> la fase de cómputo (slide 17).

---

### Checklist antes de presentar
- [ ] `gato.html` **pre‑generado** y abierto (Plan B).
- [ ] ray0 encendido, Ray iniciado, Dashboard abierto (Plan A).
- [ ] `gato_rl_ray.py` ya copiado en `~/ray-demo`.
- [ ] Una partida de prueba jugada (que la IA responde).
- [ ] Tener a mano el deck en los slides 6, 8, 12 y 16.
