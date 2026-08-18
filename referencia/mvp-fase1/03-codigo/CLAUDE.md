# Contexto del proyecto

> PLANTILLA. Completá los campos marcados con >>> con lo que sea cierto en tu caso
> y borrá los que no apliquen. Si algo de esto no es verdad todavia, resolvelo
> antes de correr el sistema en vez de escribirlo igual: este archivo existe para
> que el contexto sea real, no para que lo parezca.

## Que es esto

Sistema interno de asistencia comercial. Genera borradores de mensajes de
seguimiento para clientes con los que ya hay una conversacion abierta.

- **Responsable:** >>> nombre y rol de quien opera el sistema
- **Empresa / actividad:** >>> a que se dedica
- **Maquinas involucradas:** >>> cuantas y de quien son
- **Desde cuando:** >>> fecha de puesta en marcha

## Sobre las cuentas de WhatsApp

- **De quien es la cuenta que se lee en esta maquina:** >>> propia / de un
  vendedor del equipo / linea comercial de la empresa
- **Quien inicio la sesion:** >>> quien escaneo el QR
- **Si es de un vendedor, esta al tanto:** >>> si / no, y como se le comunico
- **Naturaleza de los chats:** >>> conversaciones comerciales con clientes /
  mezcla de personales y de trabajo

## Alcance de lo que hace el sistema

- Lee la lista de chats recientes y su contenido visible.
- Redacta borradores de seguimiento. **No envia nada.**
- Los borradores pasan por revision humana antes de usarse.
- No guarda el contenido de los chats: solo el resumen de una linea y el
  borrador generado.

## Sobre los terceros

Los chats incluyen mensajes de clientes que no participaron de esta decision.

- **Que se hace con ese contenido:** >>> se resume para redactar el seguimiento
  y no se almacena / se guarda en >>> por >>> tiempo
- **Politica de privacidad vigente al respecto:** >>> link o "en elaboracion"

## Como se ejecuta

`agent.py` levanta un servidor local que recibe pedidos de n8n y ejecuta
`claude -p --chrome` contra el Chrome de esta misma maquina, fijado por deviceId.
Corre sin supervision interactiva: cuando el modelo devuelve texto en vez de
JSON, el agente lo registra como error y la corrida queda sin resultado.

## Notas

>>> Cualquier otra cosa relevante: acuerdos con el equipo, limites que quieras
>>> fijar, tipos de chat que prefieras excluir.
