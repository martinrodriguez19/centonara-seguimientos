# 07 — Convenciones

> Leer antes del primer pull request.

---

## 1. Git

### Ramas

```
main                      → producción. Es lo único que se despliega
feat/{descripcion}          feat/verificacion-de-identidad
fix/{descripcion}           fix/normalizacion-e164
spike/{descripcion}         spike/envio-macos      ← se borra, no se mergea
```

**No hay `develop`.** No hay staging, así que no hay nada que integrar antes de producción. Se
trabaja en una rama corta y se mergea a `main` cuando pasa el CI.

> Esto decía la verdad desde el principio, pero **GitHub no lo sabía**: la rama por defecto del
> repositorio siguió siendo `develop` hasta el 24 de agosto de 2026, mientras `develop` se quedaba
> 37 commits atrás, congelada en el sprint 0.
>
> Consecuencia: `git clone` sin `-b` traía el esqueleto, y la página del repositorio en GitHub
> mostraba una versión vieja. Costó un rato de confusión instalando la primera Mac —el instalador
> "no existía"— hasta que se miró la rama.
>
> Corregido: la rama por defecto es `main`, y `develop` se renombró a **`sprint-0-congelado`**,
> que dice lo que es. Tiene un commit propio (`d6cc0c8`, un arreglo de n8n) que no está en `main`;
> se conserva por eso, aunque n8n ya no exista en el proyecto (D18).
>
> La lección, que vale más que el arreglo: **una convención escrita que la herramienta no aplica
> no es una convención, es una intención.**

Las ramas `spike/` son para explorar. Pueden tener código feo, código a medias y experimentos. No
se mergean: lo que sirve se reescribe.

### Commits — Conventional Commits, en español

```
feat(backend): agregar guardrail de anti-duplicados
fix(agente): resolver el número del chat cuando no está agendado
docs(fases): actualizar el criterio de salida de F3
test(guardrails): cubrir el tope diario por máquina
```

Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`.

### Pull requests

```markdown
## Qué hace
## Por qué
## Cómo se probó
## ¿Toca el camino de envío?  Sí / No
## Checklist
- [ ] Tests pasan
- [ ] Lint pasa
- [ ] Si toca guardrails: hay un test que intenta violarlo
- [ ] Si toca la API: 02-ARQUITECTURA §4 actualizado
- [ ] Si es una decisión: 06-DECISIONES actualizado
```

**Los PR que tocan la verificación de identidad los mira alguien más antes de mergear.** Es el
único lugar del código donde eso se pide, y es a propósito: si se pide en todos lados, se deja de
mirar en el que importa.

"Camino de envío" es: `core/guardrails.py`, `core/estados.py`, `agente/adaptadores/*`, y cualquier
endpoint que encole un job `ENVIAR`.

---

## 2. Despliegue

Se despliega a producción desde `main`, cuando está listo. **Sin ventana horaria y sin días
prohibidos**: el sistema no corre solo, así que un despliegue roto no manda mensajes — manda cero
mensajes hasta que alguien apriete el botón.

Antes de desplegar algo que toca el envío, poné `destinos_permitidos` en los números de prueba.

---

## 3. Código Python

- Formato y lint: **Ruff**, línea de 100. Corre en CI.
- Tipado en funciones públicas.
- **Nombres de dominio en español** (`mensajes`, `vendedor`, `corrida`), estructura técnica en
  inglés (`app`, `tests`, `api`).
- Pydantic v2 para todo lo que entra o sale de la API. Nada de `dict` sin esquema.
- Async en todo el backend. Nunca una llamada bloqueante en un endpoint.

### Prohibido en el camino de envío

```python
except Exception:
    pass                # esto es un incidente, no un atajo
```

Toda excepción se registra y devuelve un resultado explícito. El sistema falla cerrado (R2).

### Prohibido en la cola

```python
time.sleep(60)          # un ritmo fijo es lo que dispara bloqueos
```

El espaciado se implementa con `disponible_desde` y jitter, no bloqueando un hilo.

---

## 4. Código TypeScript

- Prettier + ESLint con la config de Next. `strict: true`, nada de `any` sin justificar.
- Componentes de servidor por defecto; `"use client"` sólo cuando hace falta.
- Los textos de la interfaz en español, en `lib/textos.ts`. El cliente va a querer cambiar palabras.

---

## 5. Tests

| Qué | Cobertura exigida |
|---|---|
| `core/guardrails.py` | **100%** |
| `core/estados.py` | **100%** |
| `core/contactos.py` (E.164) | **100%** |
| Todo lo demás | sin umbral |

La cobertura por la cobertura no sirve. Esos tres archivos son los que, si fallan, mandan un
mensaje que no debía salir.

**Un test del camino feliz no prueba un guardrail.** Cada guardrail tiene un test que **intenta
violarlo** y verifica que falla.

Ningún test toca WhatsApp real, nunca. El modo prueba y la lista de destinos permitidos existen
para eso.

---

## 6. Logs

`structlog`, JSON fuera de local. Nunca un token, nunca el texto completo de un mensaje de un
cliente.

Todo resultado de job incluye `raw` y `stderr`, **también en éxito**. Es lo primero que se lee
cuando algo falla, y sólo está ahí si se puso desde el principio.
