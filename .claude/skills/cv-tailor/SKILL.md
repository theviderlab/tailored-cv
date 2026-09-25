---
name: cv-tailor
description: Adapta el CV y la cover letter base a un aviso de empleo específico (a partir de un link o texto pegado) y genera los PDFs. Usar cuando el usuario pida adaptar, tailorizar, personalizar o generar el CV / cover letter para una postulación, o pase un link de una oferta de trabajo. También para agregar skills, logros o datos al perfil profesional (workspace/profile/) o actualizar el estado de una postulación.
---

# CV Tailor

Adapta el CV y la cover letter a una oferta concreta y produce los PDFs listos para enviar. Regla de oro: **nunca inventes datos**. Todo lo que quede en el CV debe salir del perfil (`workspace/profile/`) o de una respuesta explícita del usuario en la conversación.

## Fuentes

- **Perfil (fuente de verdad, crece con el uso):** `workspace/profile/`. Ver `workspace/profile/README.md` para qué va en cada archivo y sus reglas.
  - `skills.md`, `experience.md`, `projects.md`, `education.md`, `stories.md`, `facts.md`, `gaps.md`.
- **CV base (selección por defecto, hasta dos páginas):** `workspace/cv-base.md`. Es el punto de partida de formato, orden y tono; el contenido se puede ampliar o reemplazar con lo que haya en el perfil.
- **Cover letter base:** `workspace/cover-letter-base.md`. Punto de partida; los bloques alternativos están en `stories.md`.
- **Registro de postulaciones:** `workspace/applications.md`.
- **Buenas prácticas ATS:** `docs/ats-guidelines.md`. Aplícalas al redactar o reescribir bullets, perfil y skills (sobre todo B1–B7, K1, K2). La auditoría completa del perfil la hace la skill `profile-audit`.

Todo lo personal vive en `workspace/`, que está en el `.gitignore` del repo (el usuario puede versionarlo aparte, como repo privado propio). Nunca copies datos del usuario fuera de `workspace/`.

### Primera vez (si `workspace/` no existe)

1. Copia `workspace.example/` a `workspace/`.
2. Pídele al usuario su CV actual (pegado, o la ruta a un md/pdf) y con eso completa `workspace/cv-base.md` respetando el contrato del markdown de abajo, y los archivos de `workspace/profile/` (experiencia, skills, educación, datos de contacto en `facts.md`). Usa `origen: CV inicial (<AAAA-MM-DD>)`.
3. Si tiene una cover letter, úsala como `workspace/cover-letter-base.md`; si no, arma una breve con lo del perfil y pídele que la apruebe.
4. Genera el CV base (`npm run cv -- ../workspace/cv-base.md` desde `cv/`) para verificar que el build funciona, y sugiere correr `profile-audit`.

El CV base y la cover letter base **no se editan** salvo que el usuario lo pida. El perfil y el registro **sí se editan** durante el flujo, siguiendo las reglas de abajo. Cada postulación genera sus archivos (md y pdf) en su propia subcarpeta `workspace/output/<empresa>-<rol>/`.

## Contrato del markdown (obligatorio para que el build funcione)

El script `cv/build-cv.js` mapea el markdown a una plantilla HTML de una columna optimizada para ATS. Los títulos de sección deben coincidir **exactamente** (incluidas mayúsculas y el `&`):

```
# <Nombre completo>
**<Headline>**

- **Location:** <país>
- **Cell:** <teléfono>
- **Email:** <email>
- **LinkedIn:** [<texto>](<url>)
- **GitHub:** [<texto>](<url>)

## Executive Profile
<párrafo>

## Core Competencies & Technical Skills
- **<categoría>:** <habilidades>
- ...

## Professional Experience
### <Rol> — *<Organización>* (<Fechas>)
- **<Etiqueta>:** <descripción>
- ...

### <Rol 2> — *<Org 2>* (<Fechas 2>)
- ...

## Community Leadership & Tech Advocacy
**<Título> | <Comunidad>** (<Frecuencia>)
- <bullet>
- ...

## Education & Certifications
- **<Título>** | <institución> (<año>) — <nota>
- ...
```

- La línea de contacto usa `- **Clave:** valor`. LinkedIn/GitHub llevan link en markdown; Email/Cell/Location van sin link.
- Cada `###` de experiencia sigue exactamente `Rol — *Org* (Fechas)` (separado por em dash `—`). Fechas en formato `MMM YYYY – MMM YYYY` o `MMM YYYY – Present` cuando el perfil tiene los meses; si solo tiene el año, se usa el año.
- Usa `**negrita**` para las etiquetas de cada bullet (p. ej. `**End-to-End AI Leadership:** ...`).

## Contrato de la cover letter (obligatorio)

`cv/build-cover-letter.js` parsea la carta; el nombre, headline y contacto los toma **automáticamente del CV base** (no se duplican en la carta). Formato de `workspace/output/<empresa>-<rol>/cover-letter-<empresa>-<rol>.md`:

```
<Saludo>

<Párrafo 1>

<Párrafo 2>

...

Best regards,
<Tu nombre>
```

- Párrafos separados por línea en blanco.
- El **primer** párrafo es el saludo (p. ej. `Dear Hiring Team,`).
- El **último** bloque es el cierre: su primera línea es la despedida (`Best regards,`) y las restantes son la firma (nombre).
- Todo lo del medio son párrafos del cuerpo.

## Flujo

1. **Lee las fuentes:** todo `workspace/profile/`, el CV base, la cover letter base y `workspace/applications.md` (para detectar si ya se postuló a esa empresa).

2. **Obtén el aviso.** Si el usuario da un link, usa la herramienta de fetch web (`WebFetch` en Claude Code, `webfetch` en OpenCode). Si el fetch falla (LinkedIn bloquea bots, login, JS), pídele que pegue el texto del aviso.

3. **Cruza el aviso contra el perfil.** Extrae los requisitos del aviso (skills, herramientas, experiencia, idiomas, condiciones como ciudad o modalidad) y clasifícalos:
   - **En el perfil:** se pueden usar directamente.
   - **En `gaps.md`:** no se usan y no se pregunta. Si es un requisito central, menciónalo al usuario como brecha.
   - **En el perfil con `nivel: ?` o `evidencia: ?`**, y el requisito es importante en el aviso: pregunta el detalle (una línea basta).
   - **No aparece en ningún lado:** pregunta.

   Haz **todas las preguntas juntas en un solo mensaje**, cortas y concretas. Por ejemplo:
   > El aviso pide estas cosas que no tengo registradas:
   > 1. SQL — ¿lo usás? Si sí, ¿dónde o cuánto? (opcional)
   > 2. Kubernetes — ¿lo usás?
   > 3. Modalidad híbrida en Madrid — ¿te sirve?

   Si la herramienta de preguntas estructuradas (`AskUserQuestion`) está disponible y son pocas preguntas de sí/no, puedes usarla.

4. **Actualiza el perfil con las respuestas** (antes de escribir el CV):
   - **Sí** → agrega o completa la entrada en el archivo que corresponda (`skills.md`, `experience.md`, `facts.md`…) con el formato de ese archivo y `origen: postulación <empresa>-<rol> (<AAAA-MM-DD>)`. Un "sí" sin detalle es suficiente: se guarda con `nivel: ?` / `evidencia: ?`.
   - **No** → agrégalo a `gaps.md` con el mismo formato de origen.
   - Si el usuario da un logro, métrica o anécdota nueva, guárdala también (`experience.md` o `stories.md`), aunque no se use en esta postulación.
   - Si una respuesta contradice algo del perfil, actualiza la entrada existente (no dupliques) y avísale.
   - Muestra al usuario un resumen de una línea por cambio en el perfil.

5. **Propón adaptaciones** del CV y la cover letter para ese aviso:
   - Parte del CV base y reemplaza o suma contenido del perfil que encaje mejor con la oferta (skills, bullets de `experience.md`, bloques de `stories.md`).
   - Reordena o reescribe bullets para priorizar lo que pide la oferta.
   - Ajusta el perfil/headline al rol y la empresa.
   - Usa SOLO información del perfil o de la conversación. Si falta algo, pregunta.
   - Redacta siguiendo `docs/ats-guidelines.md`: sigla y forma completa en la primera aparición, las keywords del aviso con la misma forma que usa el aviso, nada de afirmaciones absolutas, y métricas solo si están en el perfil.
   - Recuerda el límite de dos páginas del CV: sumar algo suele implicar quitar otra cosa.

6. **Escribe los archivos nuevos** en una subcarpeta propia de la postulación, `workspace/output/<empresa>-<rol>/` (no toques los base; crea la carpeta si no existe). Nunca escribas archivos sueltos en la raíz de `workspace/output/`:
   - `workspace/output/<empresa>-<rol>/cv-<empresa>-<rol>.md`
   - `workspace/output/<empresa>-<rol>/cover-letter-<empresa>-<rol>.md`
   - (empresa y rol en slug: minúsculas, sin espacios ni acentos, separados por `-`. Los nombres de archivo mantienen el slug para que los PDFs sigan siendo identificables al enviarlos.)
   - Si la carpeta ya existe (misma empresa y rol), pregúntale al usuario si sobreescribir o usar un sufijo (p. ej. `-2`).

7. **Verifica antes de generar.** Compara el archivo nuevo contra el CV base y produce un reporte breve:
   - Lista cada cambio sustantivo (frase, dato, número, link, nombre).
   - Para cada dato nuevo, indica su origen (archivo del perfil o respuesta del usuario en esta conversación).
   - Marca explícitamente cualquier cosa que no sea rastreable al perfil o a la conversación. Si existe algo así, corrígelo o pregunta.
   - Chequeo ATS rápido: siglas clave con su forma completa, keywords centrales del aviso presentes en skills y en al menos un bullet, formato de fechas consistente.

8. **Genera los PDFs tras la aprobación del usuario.** Cuando el usuario confirme, ejecuta desde `cv/`:

   ```
   npm run cv -- ../workspace/output/<empresa>-<rol>/cv-<empresa>-<rol>.md
   npm run cover -- ../workspace/output/<empresa>-<rol>/cover-letter-<empresa>-<rol>.md
   ```

   Cada PDF se crea junto a su `.md`, dentro de la subcarpeta de la postulación. Si el CV pasa de 2 páginas o la carta reporta overflow, recorta ese texto y regenera.

9. **Registra la postulación** en `workspace/applications.md`: agrega una fila arriba con fecha, empresa, rol, carpeta, link del aviso (si lo hay), estado `enviada` (o `?` si el usuario no confirmó el envío) y notas breves (p. ej. idioma).

10. **Sugiere mejoras al CV base (opcional).** Si en el registro ves que algo se agregó en 3 o más postulaciones recientes (p. ej. SQL o LangChain), o que un bullet de la base se quita siempre, sugiérele al usuario en una línea actualizar el CV base. No lo edites sin su aprobación.

## Otros usos

- **"Agregá X a mi perfil" / "ahora sé X":** actualiza el archivo del perfil que corresponda con `origen: conversación (<fecha>)`, sin armar un CV.
- **"Actualizá el estado de la postulación a X":** edita la fila en `workspace/applications.md`.
- **"Revisá / auditá / mejorá mi perfil para ATS"** (sin aviso): no es de esta skill, usa `profile-audit`.
- Si en el paso 3 aparecen datos flojos que no pide el aviso (fechas sin mes, bullets sin métricas), no los preguntes ahora: sugiere en una línea correr `profile-audit`.

## Notas del build

- Requiere Node (dep `markdown-it`) y Chrome/Edge instalados. `npm install` en `cv/` la primera vez.
- `npm run cv` genera **un PDF** optimizado para ATS, `<nombre>.pdf`, junto al markdown (una columna; plantilla `cv/design/template.html` + `style.css`). Usa títulos estándar (Summary, Skills, Professional Experience, Education & Certifications, Volunteer Experience) sin cambiar el contrato del markdown.
- **El CV puede ocupar hasta 2 páginas.** Si pasa de 2, el build **termina con código 1**: acorta el markdown (recorta bullets o reescribe el perfil) hasta que salga limpio, antes de entregar el PDF.
- El build de la cover letter (`npm run cover`) usa como base de identidad `workspace/cv-base.md`; se puede sobreescribir con `CV_BASE=...` o un segundo argumento.
- Si el usuario quiere inspeccionar el HTML intermedio: `CV_KEEP_HTML=1 npm run cv -- <md>` conserva `cv/design/.tmp_cv.html` (o `.tmp_cover.html` para la carta).
- Los estilos viven en `cv/design/style.css` (CV) y `cv/design/style-cover-letter.css`; no edites el CSS salvo que el usuario lo pida.
