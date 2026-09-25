---
name: profile-audit
description: Audita el perfil profesional (workspace/profile/) contra las buenas prácticas ATS, detecta mejoras (fechas sin mes, empleadores ambiguos, bullets sin métricas, siglas sin forma completa, duplicados, datos faltantes) y le hace al usuario las preguntas necesarias para completarlas. Usar cuando el usuario pida revisar, auditar, mejorar o pulir su perfil, su fuente de verdad o su CV para ATS, sin un aviso de empleo concreto. Para adaptar el CV a un aviso, usar cv-tailor.
---

# Profile Audit

Revisa toda la fuente de verdad (`workspace/profile/`) contra `docs/ats-guidelines.md`, detecta mejoras y las resuelve con preguntas al usuario. Regla de oro (igual que `cv-tailor`): **nunca inventes datos**. Una fecha, métrica, cliente o nivel solo entra si el usuario lo confirma.

## Fuentes

- **Reglas:** `docs/ats-guidelines.md`. Cada hallazgo cita el ID de una regla (S1, K1, B2…) y su prioridad (P1/P2/P3).
- **Perfil:** todo `workspace/profile/` (ver `workspace/profile/README.md` para las reglas de cada archivo).
- **Estado de la auditoría:** `workspace/profile/audit.md`. Lo pendiente, lo resuelto y lo descartado en auditorías anteriores. **Léelo primero**: no se vuelve a preguntar lo descartado ni lo resuelto.
- **CV base:** `workspace/cv-base.md`. Solo para la sugerencia final (paso 7).

Si `workspace/` no existe, sigue el paso "Primera vez" de `cv-tailor` antes de auditar.

## Modos

- **Completa** (por defecto): todo el perfil.
- **Enfocada:** si el usuario acota ("solo experiencia", "solo fechas", "solo skills"), audita solo eso.
- **Continuar:** si `audit.md` tiene pendientes y el usuario dice "sigamos" o similar, retoma desde ahí sin volver a analizar todo.

## Flujo

1. **Lee** `ats-guidelines.md`, `audit.md` y todo `workspace/profile/`.

2. **Detecta hallazgos.** Recorre cada archivo y aplica las reglas. Como mínimo:
   - `experience.md`: S1 fechas, S2 un empleador por entrada, S3 empleador concreto, S4 título, S5 ubicación, B1–B8 en cada bullet (métricas, verbos, absolutos, relleno, duplicados, contexto de industria), K1 siglas, K3 skills del listado que no aparecen en ningún bullet. También las notas "Pendiente de completar".
   - `education.md`: S8 (título completo, institución completa, ubicación, fechas), S9 certificaciones (emisor, mes/año, en curso o terminada), S10 idiomas.
   - `skills.md`: K2 nombres canónicos y categorías vagas, K4 `nivel: ?` y `evidencia: ?`, K1 siglas, K5 soft skills sueltas.
   - `projects.md`: fechas, rol, stack, resultado medible, link, B4.
   - `facts.md`: S7 contacto completo (ciudad, país, teléfono con código de país).
   - Coherencia entre archivos: la misma fecha, título o nombre de empresa escritos distinto en dos lugares.

   Cada hallazgo tiene un **tipo**:
   - **Dato:** falta información que solo el usuario sabe → **pregunta** (p. ej. meses de inicio y fin).
   - **Decisión:** hay más de una forma válida de estructurarlo → **opciones** (p. ej. separar empleadores o agruparlos bajo una consultora).
   - **Redacción:** se puede mejorar con lo que ya está en el perfil → **propuesta antes/después** (p. ej. agregar la forma completa de una sigla, sacar "eliminate", fusionar duplicados). Si mejorarla necesita un dato (una métrica), primero es un **Dato**.

3. **Muestra el resumen** antes de preguntar: cantidad de hallazgos por prioridad y por archivo, y los 3–5 más importantes en una línea cada uno. Guarda la lista completa en `audit.md` como pendiente (ver formato abajo).

4. **Pregunta por tandas**, de mayor a menor prioridad (P1 → P2 → P3):
   - Tandas de 5 a 8 preguntas, agrupadas por entrada (p. ej. todo lo de un rol junto).
   - Preguntas cortas y concretas, numeradas, que se puedan contestar en una línea. Aclara que "no sé" o "saltear" es válido.
     > **Acme Corp (2013 – 2021)**
     > 1. ¿Mes de inicio y de fin? (S1)
     > 2. ¿Cuántas personas había en el equipo, o cuántos clientes/puntos de venta? (B2)
     > 3. ¿Ciudad y país? (S5)
   - Para **Decisiones** con opciones cerradas, usa `AskUserQuestion` si está disponible.
   - Las **Redacciones** van en una tanda aparte, como tabla antes/después con el ID de la regla. El usuario aprueba, rechaza o edita cada una.
   - Después de cada tanda, aplica los cambios (paso 5) y pregunta si seguir con la siguiente.

5. **Aplica los cambios** al perfil:
   - Edita la entrada existente, no la dupliques. Respeta el formato de cada archivo.
   - Datos nuevos: agrega `origen: auditoría ATS (<AAAA-MM-DD>)`. Si la entrada ya tenía `origen:`, lo conservas y agregas el nuevo al lado.
   - Reescrituras aprobadas: reemplaza el texto y agrega `revisado: auditoría ATS (<AAAA-MM-DD>)` en la línea de origen del bullet.
   - Separar o renombrar empleadores: mantén todos los bullets, redistribuidos según la respuesta del usuario.
   - Una métrica que el usuario da de forma aproximada se guarda aproximada (`~30%`, `10+ clients`), nunca redondeada hacia arriba.
   - "No sé" o "prefiero no" → el hallazgo pasa a **Descartado** en `audit.md` con el motivo, para no volver a preguntar.
   - Si el usuario menciona un logro, dato o anécdota nuevos, guárdalos también (`experience.md`, `stories.md`, `facts.md`).
   - Muestra un resumen de una línea por cambio.

6. **Actualiza `audit.md`**: mueve lo aplicado a Resuelto, lo rechazado a Descartado, y deja el resto como Pendiente con la fecha de la última sesión.

7. **Sugiere cambios al CV base** (al final de la sesión, o cuando el usuario pare): lista qué mejoras del perfil conviene llevar a `workspace/cv-base.md` (fechas con mes, empleadores corregidos, bullets reescritos). **No lo edites sin aprobación.** Si se aprueba, edítalo respetando el contrato del markdown de `cv-tailor` y verifica con el build desde `cv/`:
   ```
   npm run cv -- ../workspace/cv-base.md
   ```
   El CV visual tiene que salir en una página y el ATS en dos como máximo. Si hay overflow, recorta y regenera. (Los PDFs quedan junto al md en `workspace/`; avísale al usuario.)

## Formato de `workspace/profile/audit.md`

```
## Pendiente
- [ID-hallazgo] <archivo> · <entrada> · <regla> (<prioridad>) · <tipo> — <qué falta o qué mejorar>

## Resuelto
- [ID-hallazgo] <archivo> · <entrada> · <regla> — <qué se hizo> · <AAAA-MM-DD>

## Descartado
- [ID-hallazgo] <archivo> · <entrada> · <regla> — <motivo: no sabe / prefiere no / no aplica> · <AAAA-MM-DD>
```

El ID del hallazgo es un número correlativo (`A1`, `A2`…). No se reutiliza.

## Reglas

- El contenido del perfil va en inglés; las preguntas y notas internas en español.
- No edites el CV base ni la cover letter base sin aprobación explícita.
- Una reescritura no puede cambiar el significado de un logro ni sumar alcance que el usuario no confirmó.
- Si al actualizar las reglas ATS surge una práctica nueva, propónla como cambio en `docs/ats-guidelines.md`; no la apliques en silencio.
