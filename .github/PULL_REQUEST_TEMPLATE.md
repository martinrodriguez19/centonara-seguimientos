## Qué hace

## Por qué

## Cómo se probó

## ¿Toca el camino de envío?  Sí / No

<!-- Camino de envío: core/guardrails.py, core/estados.py, core/triage.py,
     agente/adaptadores/*, y cualquier endpoint que encole un job ENVIAR.
     Si es Sí: hacen falta DOS revisores (08 §1). -->

## Checklist

- [ ] Tests pasan
- [ ] Lint pasa
- [ ] Si toca guardrails: hay un test que intenta violarlo
- [ ] Si toca la API: `docs/04-CONTRATOS-API.md` actualizado
- [ ] Si es una decisión: `docs/10-DECISIONES.md` actualizado
