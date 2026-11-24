# Cómo contribuir a Poki Koa (backend)

Esta guía explica cómo trabajar con ramas, commits y pull requests (PR) en este repositorio. La idea es simple: **ningún cambio llega a `main` sin pasar por un PR con la CI en verde**.

## 1. Antes de empezar

1. Configura tu identidad de Git con tu correo real (no el de la plantilla):

   ```bash
   git config --global user.name "Nombre Apellido"
   git config --global user.email "tu.correo.real@alumnos.uv.cl"
   ```

2. Parte siempre desde `main` actualizado:

   ```bash
   git switch main
   git pull
   ```

## 2. Ramas

Crea una rama nueva para cada cambio, **siempre desde `main`** y nunca desde otra rama de trabajo.

| Prefijo | Para qué | Ejemplo |
|---|---|---|
| `feat/` | Funcionalidad nueva | `feat/umbral-por-paciente` |
| `fix/` | Corrección de un error | `fix/validacion-codigo-cuna` |
| `docs/` | Solo documentación | `docs/guia-despliegue` |
| `refactor/` | Cambio interno sin cambiar el comportamiento | `refactor/roles-compartidos` |

- Usa minúsculas y guiones, sin espacios ni tildes.
- Si la rama resuelve una issue, incluye el número: `fix/85-validaciones-cunas`.
- **Ojo:** la CI se ejecuta automáticamente al hacer *push* solo en `main`, `rewrite/**`, `feat/**` y `fix/**`. Si usas otro prefijo, corre tú la verificación local (sección 4) antes de abrir el PR.

## 3. Commits

- Un commit = un cambio con sentido propio. Evita commits gigantes que tocan decenas de archivos de distintas apps.
- Mensaje en español, en imperativo y con prefijo:

  ```
  feat: agregar exportación CSV de la bitácora
  fix: devolver 400 cuando el estado de la cuna no es válido
  docs: agregar guía de contribución
  test: cubrir la liberación de cuna sin paciente
  refactor: usar CLINICAL_OR_ADMIN en devices/views.py
  ```

- No subas archivos generados ni locales: `db.sqlite3`, `.env`, `__pycache__/`, `.venv/`, capturas, planillas de tareas de clase.

## 4. Verificación local antes de abrir un PR

Desde la raíz del repositorio, ejecuta lo mismo que la CI:

```bash
uv sync --locked
uv run ruff format src                      # formatea el código
uv run ruff check src                       # debe terminar con 0 errores
uv run ruff format --check src              # no debe quedar nada por formatear
uv run poki_koa makemigrations --check --dry-run
uv run coverage run -m pytest               # todas las pruebas deben pasar
uv run coverage report                      # la cobertura no puede bajar del mínimo de la CI
```

Si cambiaste vistas o serializadores, verifica también que el contrato OpenAPI esté al día:

```bash
uv run poki_koa spectacular --file schema-local.yml
# compara schema-local.yml con openapi/schema.yml; si cambió, actualiza openapi/schema.yml en el mismo PR
```

Errores típicos que hacen fallar la CI:

- `W292`: falta un salto de línea al final del archivo.
- `D417`: un docstring con sección `Args:` no documenta todos los parámetros.
- Archivos sin formatear: se arreglan con `uv run ruff format src`.

## 5. Reglas de código que no se negocian

- **Las validaciones de datos del usuario lanzan `DomainError`**, que la API convierte en una respuesta 400 con un mensaje claro en español. Nunca uses `assert` para validar entrada: con `assert` el usuario recibe un error 500 y, si Python se ejecuta con `-O`, la validación desaparece.
- Las reglas de negocio (roles, estados, bloqueos, auditoría) viven en los `services.py`, no en las vistas.
- Para restringir por rol, usa los conjuntos de `accounts/roles.py` (`CLINICAL_STAFF`, `CLINICAL_OR_ADMIN`, etc.) y `require_role`, en vez de escribir los roles a mano.
- Todo cambio de comportamiento viene con su prueba.

## 6. Pull requests

1. Sube tu rama: `git push -u origin <nombre-de-la-rama>`.
2. En GitHub, abre el PR hacia `main`.
3. En la descripción indica:
   - **Qué cambia** y **por qué** (enlaza la issue con `Closes #NN` si corresponde).
   - **Cómo se probó** (comandos ejecutados y resultado).
4. Mantén el PR pequeño. Si toca varias apps (`devices`, `alerts`, `patients`…), mejor un PR por app.
5. Espera la CI en verde y al menos **una aprobación** de otra persona del equipo antes de integrar.
6. Si la revisión pide cambios, haz nuevos commits en la misma rama; el PR se actualiza solo.

## 7. Lista rápida antes de pedir revisión

- [ ] La rama salió de `main` actualizado.
- [ ] El PR solo contiene los archivos que quería cambiar (revisa la pestaña *Files changed*).
- [ ] `ruff check`, `ruff format --check` y `pytest` pasan en local.
- [ ] Las validaciones de entrada usan `DomainError`, no `assert`.
- [ ] La descripción del PR dice qué cambia, por qué y cómo se probó.
