# tailored-cv

Adapta tu CV y tu cover letter a cada aviso de empleo con un agente de IA (Claude Code u OpenCode), y genera PDFs listos para enviar: uno con diseño visual y otro optimizado para ATS.

La idea central es un **perfil profesional que crece con el uso**: cada vez que un aviso pide algo que no está registrado, el agente te pregunta, guarda la respuesta y la reutiliza en las próximas postulaciones. Nunca inventa datos: todo lo que sale en el CV viene de tu perfil o de algo que confirmaste.

## Cómo funciona

| Pieza | Qué hace |
|---|---|
| `.claude/skills/cv-tailor/` | Lee el aviso (link o texto), lo cruza con tu perfil, te pregunta lo que falta, escribe el CV y la carta adaptados y genera los PDFs. |
| `.claude/skills/profile-audit/` | Revisa tu perfil contra buenas prácticas ATS y te hace las preguntas para mejorarlo. |
| `docs/ats-guidelines.md` | Las reglas ATS que aplican las dos skills. |
| `cv/` | Build markdown → PDF con Node y Chrome/Edge headless. |
| `workspace.example/` | Plantilla vacía de tu espacio personal. |
| `workspace/` | **Tu** espacio: perfil, CV base, postulaciones y PDFs generados. Está en el `.gitignore`. |

## Primeros pasos

Requisitos: Node 18+ y Chrome o Edge instalados.

```sh
git clone https://github.com/theviderlab/tailored-cv.git
cd tailored-cv
cp -r workspace.example workspace
cd cv && npm install
```

Después abrí el proyecto con Claude Code y pedile algo como *"armá mi perfil a partir de este CV"* (pegando tu CV) o directamente *"adaptá mi CV a este aviso: <link>"*. Si `workspace/` no existe, la skill la crea desde la plantilla y te guía.

Generar un PDF a mano:

```sh
cd cv
npm run cv -- ../workspace/cv-base.md          # CV visual + versión ATS
npm run cover -- ../workspace/cover-letter-base.md
```

## Backup de tus datos (opcional, recomendado)

`workspace/` queda fuera de este repo, así que podés versionarlo como un repo **privado** independiente:

```sh
cd workspace
git init
git add .
git commit -m "Initial profile"
gh repo create <tu-usuario>/tailored-cv-workspace --private --source . --push
```

Desde ahí, los cambios a la herramienta se commitean en la raíz y los cambios a tus datos, dentro de `workspace/`.

### Red de seguridad contra filtraciones

El hook `.githooks/pre-commit` bloquea cualquier commit al repo de la herramienta que incluya archivos de `workspace/` o texto que coincida con los patrones de `workspace/.private-patterns` (tu nombre, email, teléfono…; uno por línea). Activalo una vez por clon:

```sh
git config core.hooksPath .githooks
```

## Idioma

Las skills y las notas internas están en español; el contenido del CV va en el idioma del aviso (normalmente inglés).
