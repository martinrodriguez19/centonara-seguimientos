# 08 — Convenciones

> Leer antes del primer pull request.

---

## 1. Git

### Ramas

```
main          → producción. Protegida. Sólo merge desde develop vía PR
develop       → integración. Es lo que corre en staging
feat/{sprint}-{descripcion}     feat/s3-sala-de-salida
fix/{descripcion}               fix/normalizacion-e164
```

### Commits — Conventional Commits, en español

```
feat(backend): agregar guardrail de anti-duplicados
fix(agente): corregir encoding en Windows
docs(sprints): completar criterios del sprint 4
test(guardrails): cubrir el tope diario por máquina
```

Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`.

### Pull requests

Plantilla obligatoria:

```markdown
## Qué hace
## Por qué
## Cómo se probó
## ¿Toca el camino de envío?  Sí / No
## Checklist
- [ ] Tests pasan
- [ ] Lint pasa
- [ ] Si toca guardrails: hay un test que intenta violarlo
- [ ] Si toca la API: 04-CONTRATOS-API.md actualizado
- [ ] Si es una decisión: 10-DECISIONES.md actualizado
```

**Todo PR que toque el camino de envío requiere dos revisores.** El resto, uno. "Camino de envío"
son: `core/guardrails.py`, `core/estados.py`, `core/triage.py`, `agente/adaptadores/*`, y cualquier
endpoint que encole un job `ENVIAR`.

---

## 2. Código Python

- Formato y lint: **Ruff** (línea de 100). Corre en CI.
- Tipado obligatorio en funciones públicas. `mypy` en modo no estricto.
- **Nombres de dominio en español** (`mensajes`, `vendedor`, `guardrails`), estructura técnica en
  inglés (`app`, `tests`, `api`). Suena raro leerlo la primera vez; es mucho peor tener que
  traducir mentalmente entre lo que dice el cliente y lo que dice el código.
- Pydantic v2 para todo lo que entra o sale de la API. Nada de `dict` sin esquema.
- Async en todo el backend. Nunca una llamada bloqueante en un endpoint.

### Prohibido en el camino de envío

```python
except Exception:
    pass                # ← esto es un incidente, no un atajo
```

Toda excepción se registra y devuelve un resultado explícito. El sistema falla cerrado (R3).

---

## 3. Código TypeScript

- Formato: Prettier. Lint: ESLint con la config de Next.
- `strict: true`. Nada de `any` sin un comentario que lo justifique.
- Componentes de servidor por defecto; `"use client"` sólo cuando hace falta.
- Estado del servidor: TanStack Query. Nada de `useEffect` con `fetch`.
- Los textos de la interfaz en español, en un solo archivo (`lib/textos.ts`). El cliente va a
  querer cambiar palabras.

---

## 4. Tests

| Qué | Cobertura exigida | Cuándo |
|---|---|---|
| `core/guardrails.py` | **100%** | Bloqueante para el Sprint 6 |
| `core/estados.py` | **100%** | Bloqueante para el Sprint 6 |
| `core/contactos.py` | **100%** | Bloqueante para el Sprint 1 |
| Resto del backend | sin umbral | — |
| Frontend | E2E de los flujos críticos | Sprint 3 |

**Un test por guardrail que intenta violarlo y verifica que falla.** No alcanza con probar que el
camino feliz funciona.

```python
async def test_g1_rechaza_placeholder_sin_resolver():
    msg = construir_mensaje(texto="Hola {nombre}, quería...")
    with pytest.raises(GuardrailViolado) as e:
        await validar(msg)
    assert e.value.codigo == "GUARDRAIL_PLACEHOLDER"
```

Los tests del camino de envío usan `DryRunAdapter`. **Ningún test toca WhatsApp real, nunca.**

---

## 5. Definición de terminado

Una tarea está terminada cuando:

- [ ] El código está en `develop` vía PR aprobado
- [ ] Los tests pasan en CI
- [ ] Si toca guardrails: hay un test que intenta violarlo
- [ ] Si toca la API: `04-CONTRATOS-API.md` está actualizado
- [ ] Si toca el agente: se probó en una máquina Windows real, no sólo en simulado
- [ ] Si es una decisión de producto: está en `10-DECISIONES.md`
- [ ] Alguien más que el autor lo ejecutó y funcionó

El último punto es el que más se saltea y el que más problemas evita.

---

## 6. Entornos

| Entorno | Dónde | Datos | Envía |
|---|---|---|---|
| Local | tu máquina | seed falso | **nunca** |
| Staging | Render, servicio separado | falsos + 1 línea de prueba | sólo modo prueba |
| Producción | Render | reales | sí |

`ENTORNO=produccion` es la única variable que habilita envío real. En local y staging el backend
rechaza encolar jobs de envío real aunque se lo pidan.

---

## 7. Despliegue

```
push a develop  → CI → tests → build → deploy automático a staging
merge a main    → CI → tests → build → deploy MANUAL a producción
```

El auto-deploy de Render está **desactivado**: el despliegue lo dispara GitHub Actions tras pasar
lint y tests (D15). Si no, un push con los tests rotos llegaría igual a staging.

El despliegue a producción es manual y **nunca se hace después de las 12:00** ni un viernes. Esto
está implementado como **guarda en el workflow**, no como disciplina: falla fuera de ventana salvo
que se pase `force: true`. El override existe a propósito, para el día que haya que arreglar algo
urgente, y queda registrado en el log. La
corrida sale a las 13:00; desplegar dos horas antes no deja margen para revertir.

Rollback: revertir al deploy anterior desde el panel de Render o por su API. Probado en el Sprint 0, no la primera vez que
haga falta.

---

## 8. Ceremonias

| Cuándo | Qué | Duración |
|---|---|---|
| Lunes | Planificación del sprint | 45 min |
| Diario | Sincronización | 10 min |
| Viernes | Demo y retrospectiva | 45 min |

En la demo se muestra **funcionando**, no en diapositivas. Si no se puede mostrar, no está
terminado.

---

## 9. Cómo escalar un problema

| Situación | Qué hacer |
|---|---|
| Duda técnica | Preguntá en el canal del equipo. No adivines |
| Algo no está definido en la documentación | Es un hueco de la documentación. Reportalo y se define. **No lo improvises** |
| Encontrás un riesgo de que salga un mensaje indebido | **Kill switch primero, avisar después** |
| El cliente pide un cambio de comportamiento | No se implementa hasta que esté en `10-DECISIONES.md` |
| Un test de guardrail falla y no entendés por qué | No lo marques como `skip`. Escalá |
