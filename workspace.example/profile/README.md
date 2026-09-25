# Perfil profesional (fuente de verdad)

Esta carpeta guarda **todo** lo que sabés e hiciste. Crece con el uso: cada vez que la skill `cv-tailor` pregunta por algo que no estaba registrado y la respuesta es confirmada, se agrega aquí.

El CV base (`workspace/cv-base.md`) es solo **una selección de una página** de este perfil. El perfil puede tener mucho más contenido del que entra en un CV.

| Archivo | Qué contiene |
|---|---|
| `skills.md` | Habilidades técnicas y de gestión, con nivel y evidencia |
| `experience.md` | Banco de logros por rol (más bullets de los que entran en un CV) |
| `projects.md` | Proyectos, charlas, comunidad |
| `education.md` | Títulos, certificaciones, idiomas |
| `stories.md` | Anécdotas y argumentos reutilizables para cover letters |
| `facts.md` | Datos prácticos: contacto, ubicación, disponibilidad, respuestas de formularios |
| `gaps.md` | Lo que confirmaste que **no** sabés o no querés destacar (para no volver a preguntar) |
| `audit.md` | Estado de la auditoría ATS (skill `profile-audit`): pendiente, resuelto y descartado |

Las buenas prácticas ATS que se aplican a este perfil están en `docs/ats-guidelines.md`.

## Reglas

- **Nada entra sin confirmación.** Cada dato nuevo viene de una respuesta explícita del usuario.
- **Cada entrada nueva lleva su origen**: `origen: <postulación o conversación> (<AAAA-MM-DD>)`.
- El contenido va en inglés (idioma del CV); las notas internas pueden ir en español.
- Si un dato cambia (p. ej. sube el nivel de una skill), se actualiza la entrada existente, no se duplica.
- Si algo de `gaps.md` pasa a ser verdad, se mueve a `skills.md`.
- Las fechas van en formato `MMM YYYY – MMM YYYY` (o `– Present`). Si solo se conoce el año, queda el año hasta que la auditoría lo complete.
