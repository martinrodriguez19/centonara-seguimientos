## Qué hace

## Por qué

## Cómo se probó

## ¿Toca el camino de envío?  Sí / No

<!-- Camino de envío: core/guardrails.py, core/estados.py, core/triage.py,
     agente/adaptadores/*, y cualquier endpoint que encole un job ENVIAR.
     Si toca la verificación de identidad, que lo mire alguien más (07 §1). -->

## Checklist

- [ ] Tests pasan
- [ ] Lint pasa
- [ ] Si toca guardrails: hay un test que intenta violarlo
- [ ] Si toca la API: `docs/02-ARQUITECTURA.md` actualizado
- [ ] Si es una decisión: `docs/06-DECISIONES.md` actualizado
- [ ] Si toca el envío: `destinos_permitidos` quedó en los números de prueba
