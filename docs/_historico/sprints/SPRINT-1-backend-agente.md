# Sprint 1 — Backend core y agente v2

**Duración:** 2 semanas · **Puede enviar:** no, el código de envío no existe (R7)

---

## Objetivo

Que las 8 máquinas aparezcan online en el backend, tomen jobs y reporten resultados. Toda la
infraestructura de trabajo, sin ningún trabajo real todavía.

Al terminar, el sistema sabe quién está prendido y puede darle órdenes. No sabe qué órdenes dar.

---

## Tareas

### T1.1 — Modelo de datos
Todas las colecciones de `03-MODELO-DE-DATOS.md`, con sus índices, en un script de inicialización
idempotente.
**Terminado cuando:** `python -m app.db.init` crea todo y correrlo dos veces no rompe nada.

### T1.2 — Normalización de contactos ⚠
`core/contactos.py`. Función única de normalización a E.164, con tests de los formatos argentinos:
`11 4440-5036`, `+54 11 4440 5036`, `0111544405036`, `+549 11 4440-5036`, `1544405036`.
**Terminado cuando:** cobertura 100% y todos los formatos de la lista pasan.
**Por qué importa:** si esto falla, el anti-duplicados falla y un contacto recibe dos mensajes.

### T1.3 — Máquina de estados
`core/estados.py`. Todas las transiciones de `03` §1, con validación explícita. Una transición no
declarada lanza excepción.
**Terminado cuando:** existe un test que intenta cada transición inválida y verifica que falla.

### T1.4 — Cola sobre MongoDB
`core/cola.py`. Encolar, tomar de forma atómica (`findOneAndUpdate`), reportar, reintentar,
`disponible_desde` para el jitter.
**Terminado cuando:** un test con 8 consumidores concurrentes verifica que ningún job se entrega
dos veces.

### T1.5 — Autenticación de agentes
Tokens por máquina, hasheados con Argon2id. Registro, rotación, revocación.
**Terminado cuando:** un token revocado recibe `401` en el request siguiente.

### T1.6 — Endpoints del agente
`/registrar`, `/jobs/next` (long-poll de 25 s), `/jobs/{id}/result`, `/heartbeat`. Según `04` §2.
**Terminado cuando:** el long-poll retiene la conexión y devuelve apenas aparece un job, sin
esperar los 25 s completos.

### T1.7 — Agente v2: bucle de polling
Registro, bucle, heartbeat, reintentos con backoff, manejo de `204` y `423`.
**Terminado cuando:** se desconecta la red 5 minutos, se reconecta, y el agente sigue funcionando
sin reiniciar.

### T1.8 — Autodiagnóstico
Los 7 chequeos de `07-EL-AGENTE.md` §4. En Linux o macOS, los que no aplican reportan `n/a`.
**Terminado cuando:** el panel muestra qué chequeo específico falló, no un error genérico.

### T1.9 — Auditoría
`core/auditoria.py` + rol de MongoDB que sólo permite `insert` y `find` sobre esa colección.
**Terminado cuando:** un intento de `update` sobre `auditoria` falla a nivel de base de datos, no
por convención de código.

### T1.10 — Auth del panel
Auth.js con magic link, roles, JWT verificado por FastAPI. Middleware de permisos según `04` §4.
**Terminado cuando:** un usuario con rol `vendedor` recibe `403` al pedir mensajes de otro.

### T1.11 — Pantalla de salud
Estado de las 8 máquinas en tiempo real, con su diagnóstico.
**Terminado cuando:** apagar un agente simulado se refleja en el panel en menos de 60 s.

### T1.12 — Kill switch
`POST /api/sistema/pausa`. Los jobs dejan de entregarse (`423`) y los agentes abortan lo que
tengan en curso.
**Terminado cuando:** se mide el tiempo entre apretar el botón y que un agente deje de recibir
trabajo: menos de 10 s.

---

## Criterio de salida

- [ ] 8 agentes simulados aparecen online
- [ ] Toman jobs de prueba y reportan resultado, ninguno dos veces
- [ ] `test_contactos.py` y `test_estados.py` al 100%
- [ ] `auditoria` rechaza `update` a nivel de MongoDB
- [ ] Kill switch efectivo en menos de 10 s
- [ ] El agente sobrevive a un corte de red de 5 minutos

## Riesgos

| Riesgo | Mitigación |
|---|---|
| El long-poll consume conexiones | Timeout de 25 s y límite de conexiones en uvicorn. Con 8 agentes no es un problema real |
| La normalización E.164 se subestima | Es la tarea con más tests del sprint. Los formatos argentinos son un caos |
| Alguien agrega un `enviar()` "para después" | Regla R7. Se rechaza en la revisión de código |
