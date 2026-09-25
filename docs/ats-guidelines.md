# ATS Guidelines (buenas prácticas)

Reglas que usan las skills `profile-audit` (para detectar mejoras en `workspace/profile/`) y `cv-tailor` (al redactar CVs). Cada regla tiene un ID para citarla en los hallazgos de la auditoría.

Prioridad:
- **P1 — Parseo:** si falla, el ATS extrae mal el dato (fechas, empleador, título) o calcula mal los años de experiencia.
- **P2 — Match e impacto:** afecta el puntaje por keywords o cómo lo lee el reclutador después del filtro.
- **P3 — Pulido:** estilo, consistencia, redundancias.

## 1. Estructura y parseo

- **S1 (P1) — Fechas mes/año.** Formato `MMM YYYY – MMM YYYY` o `MMM YYYY – Present` (meses en inglés abreviados: Jan, Feb, Mar, Apr, May, Jun, Jul, Aug, Sep, Oct, Nov, Dec). Con solo el año, muchos ATS asumen enero o calculan mal la antigüedad. El mismo formato en todo el perfil.
- **S2 (P1) — Un empleador por entrada.** Cada entrada de experiencia es un empleador con sus fechas. Si hubo varios empleadores, van en entradas separadas. Si fue una consultora o un trabajo independiente con varios clientes, el empleador es la consultora y los clientes se nombran en los bullets o en una línea `Clients: ...`.
- **S3 (P1) — Nombre del empleador concreto.** Nada de genéricos como "Client Projects". Para independientes: nombre comercial + `(Self-employed)` o `Independent Consultant`.
- **S4 (P1) — Título de puesto reconocible.** El título real, en la forma estándar del mercado (el que alguien buscaría). Si el título interno es raro, se puede sumar el equivalente estándar, sin inflarlo.
- **S5 (P2) — Ubicación por rol.** `City, Country` o `Remote (Country)`. Los ATS la usan en los filtros. (El template actual no la muestra por rol; se guarda igual en el perfil para portales y formularios.)
- **S6 (P1) — Secciones con títulos estándar.** Summary, Skills, Professional Experience, Education, Certifications, Languages, Volunteer Experience. (La plantilla ATS ya los mapea.)
- **S7 (P1) — Contacto completo en el cuerpo.** Nombre, `City, Country`, teléfono con código de país, email y URL de LinkedIn. Sin dirección completa. Nunca en encabezado ni pie de página. (`facts.md`)
- **S8 (P1) — Educación completa.** Nombre completo del título (sin abreviar), institución con nombre completo (acrónimo entre paréntesis), ubicación y fecha de egreso (mes/año ideal, año aceptable). Los títulos en curso llevan `Expected MMM YYYY`.
- **S9 (P2) — Certificaciones.** Nombre oficial, emisor, fecha de obtención (mes/año). Si está en curso: `In progress — expected MMM YYYY`. ID o URL de credencial si existe.
- **S10 (P2) — Idiomas con nivel estándar.** CEFR (A1–C2) o Native. Certificado y año si hay.
- **S11 (P3) — Brechas de más de 6 meses.** No hace falta explicarlas en el CV, pero conviene saberlas para no dejar fechas que parezcan un error.

## 2. Keywords y skills

- **K1 (P2) — Sigla y forma completa.** La primera aparición lleva las dos: `Retrieval-Augmented Generation (RAG)`, `Natural Language Processing (NLP)`, `Model Context Protocol (MCP)`. El ATS puede buscar cualquiera de las dos.
- **K2 (P2) — Nombres canónicos.** Las herramientas se escriben como las escribe el fabricante o el mercado: `PyTorch`, `scikit-learn`, `Amazon Web Services (AWS)`, `PostgreSQL`. Nada de categorías vagas cuando se puede nombrar la herramienta (p. ej. "Cloud Infrastructure" → qué proveedor y qué servicios).
- **K3 (P2) — Skills con evidencia en contexto.** Toda skill importante del listado debería aparecer también en al menos un bullet de experiencia o proyecto. Los ATS modernos y los reclutadores ponderan el uso en contexto.
- **K4 (P2) — Nivel y años.** Muchos formularios piden años de experiencia por skill. El perfil guarda nivel y, si se puede, años o período (`2022–present`). En el CV no van barras ni puntajes.
- **K5 (P3) — Hard skills en el listado, soft skills en los bullets.** "Leadership" o "communication" se demuestran con logros, no se listan sueltos.

## 3. Bullets de experiencia

- **B1 (P2) — Fórmula acción + qué + cómo + resultado.** `<Verbo> <qué> using <tecnología/método>, <resultado medible>`.
- **B2 (P2) — Cuantificar.** %, dinero, tiempo ahorrado, usuarios, volumen (docs, requests), cantidad de clientes/proyectos, tamaño de equipo, países, presupuesto. Si no hay número exacto, un orden de magnitud confirmado por el usuario (`~`, `10+`). **Nunca inventar números.**
- **B3 (P2) — Verbo de acción fuerte al inicio.** Pasado para roles terminados, presente para el actual. Sin pronombres ("I", "my").
- **B4 (P2) — Sin afirmaciones absolutas ni inverificables.** Evitar "eliminate", "guarantee", "always", "zero". Usar "reduced X by Y" o "minimized".
- **B5 (P3) — Sin relleno ni adjetivos vacíos.** Evitar "prestigious", "complex", "overarching", "fostering a culture of", "synergy". El resultado habla solo.
- **B6 (P3) — Sin duplicados.** Dos bullets del mismo rol no dicen lo mismo con otras palabras. Se fusionan o se diferencian.
- **B7 (P3) — Largo.** 1–2 líneas por bullet (≈ 15–35 palabras). En el CV: 3–6 bullets para roles recientes, 2–3 para los de más de 10 años. (El banco del perfil puede tener más.)
- **B8 (P2) — Alcance y contexto.** Industria del cliente/empresa, tamaño, tipo de proyecto. Ayuda al match por dominio (p. ej. "insurance", "energy", "telecom").

## 4. Summary / Executive Profile

- **U1 (P2) — 3–4 líneas.** Título objetivo + años de experiencia + 3–4 especialidades con keywords + un logro o diferencial.
- **U2 (P3) — Sin primera persona ni clichés** ("passionate", "results-driven", "team player").

## 5. Qué NO hace la auditoría

- No inventa datos, métricas ni fechas. Si el usuario no sabe o no quiere, queda como está y se registra en `workspace/profile/audit.md`.
- No cambia el significado de un logro al reescribirlo.
- No edita el CV base ni la cover letter base sin aprobación.
