# Sprint 0 — Fundaciones

**Duración:** 1 semana · **Puede enviar mensajes:** no, es técnicamente imposible

---

## Objetivo

Que cualquier persona del equipo pueda clonar el repositorio, levantar todo el sistema en su
máquina en menos de 40 minutos, y desplegar a staging con un push. Nada de lógica de negocio.

## Por qué este sprint existe

Es tentador saltarlo y empezar por "lo importante". No lo hagas. Un equipo que pasa la semana 3
peleando con entornos distintos pierde más tiempo del que cuesta esta semana.

---

## Tareas

### T0.1 — Repositorio y estructura
Monorepo con la estructura de `06-ENTORNO-LOCAL.md` §2. Carpetas vacías con un `.gitkeep` y un
`README.md` de una línea explicando qué va en cada una.
**Terminado cuando:** la estructura está en `main` y coincide con la documentación.

### T0.2 — Docker Compose local
MongoDB 7, n8n y Mailpit. Volúmenes persistentes, healthchecks, red interna.
**Terminado cuando:** `docker compose -f infra/docker-compose.dev.yml up -d` levanta los tres y
`docker compose ps` los muestra healthy.

### T0.3 — Esqueleto del backend
FastAPI con `/health`, configuración por Pydantic Settings, conexión a Mongo, structlog.
**Terminado cuando:** `GET /health` devuelve `{"ok": true, "mongo": true, "entorno": "local"}`.

> Al crear `pyproject.toml`, excluir `referencia/` de `pytest` y de la cobertura. Ruff ya la
> excluye desde la raíz. Ver `13-QUE-HACER-CON-EL-MVP.md` §1, regla 3.

### T0.4 — Esqueleto del frontend
Next.js 15 + Tailwind + shadcn/ui. Una página que consulta `/health` del backend y muestra el
estado.
**Terminado cuando:** `pnpm dev` levanta y la página muestra el estado real del backend.

> Al crear la configuración, excluir `referencia/` de ESLint y del `include` de `tsconfig.json`.
> Ver `13-QUE-HACER-CON-EL-MVP.md` §1, regla 3.

### T0.5 — Esqueleto del agente
Estructura del paquete, lectura de configuración, modo `--simulado` que loguea cada 10 s.
**Terminado cuando:** corre en Linux, macOS y Windows sin cambios de código.

### T0.6 — CI
GitHub Actions: lint + tests de backend y frontend en cada PR. Bloqueante para el merge.
**Terminado cuando:** un PR con lint roto no se puede mergear.

### T0.7 — Render, Atlas y Cloudflare
Servicios en Render (backend, frontend, worker, n8n), MongoDB Atlas, dominio en Cloudflare con
proxy activo. Deploy automático a staging al pushear a `develop`.

⚠️ **Verificar antes de dar por cerrado:** que Render sostenga una conexión abierta de 25 segundos
sin cortarla (es el long-poll de los agentes) y que el worker corra como servicio permanente. Si
alguna de las dos falla, es un hallazgo bloqueante: avisar antes de seguir.

**Terminado cuando:** `https://staging.{dominio}` responde con certificado válido y una petición de
25 s no se corta.

### T0.8 — Rollback probado
Documentar y **ejecutar** el procedimiento de vuelta atrás.
**Terminado cuando:** alguien que no lo escribió lo ejecutó siguiendo el documento.

### T0.9 — Backups
Script de backup diario de MongoDB, cifrado, con retención de 30 días. **Y una restauración
probada.**
**Terminado cuando:** se restauró un backup en una base limpia y los datos están.

### T0.10 — Arrancar las dependencias externas
Enviar al cliente el pedido formal de E2 a E6 de `09-ROADMAP.md` §2.
**Terminado cuando:** el pedido está enviado por escrito y con fecha comprometida. **Especialmente
E3, E4 y E6.**

---

## Criterio de salida

- [ ] Una persona nueva clona, sigue `06-ENTORNO-LOCAL.md` y tiene todo corriendo en 40 minutos
- [ ] CI verde en `main` y `develop`
- [ ] Staging accesible con TLS
- [ ] Rollback ejecutado por alguien distinto al autor
- [ ] Restauración de backup probada
- [ ] Pedido de dependencias externas enviado

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El equipo quiere empezar "por lo importante" | Este sprint es lo importante. Sin él, cada sprint siguiente pierde días |
| La máquina Windows de pruebas no llega a tiempo | Por eso se pide en la semana 1 y no en el Sprint 4 |
| Node menor a 22 | Documentado. `nvm install 22`. Es el problema #1 del historial del MVP |
