# Sistema de Seguimiento Comercial

Un botón que hace que Claude lea los chats recientes de WhatsApp Web en las Macs de los
vendedores, redacte un seguimiento para cada uno, y los envíe desde la línea de cada vendedor.

Monorepo. Un solo `git clone` y tenés todo.

## Arrancar

Cuatro cosas instaladas: **Docker**, **Python 3.12**, [**uv**](https://docs.astral.sh/uv/)
y **Node 22 con pnpm**.

> **Node 22 o superior, no negociable.** Es el problema #1 del historial del MVP.

Primero la configuración:

```bash
cp .env.example .env
```

Abrilo y completá dos valores. `SESION_SECRET` viene vacío y `PANEL_PASSWORD`
dice `cambiar`. Los dos **fallan cerrados** —sin secreto, firmar una cookie
lanza un error explícito; una contraseña vacía nunca valida— así que no hay
forma de arrancar abierto por olvido, pero tampoco vas a entrar al panel hasta
completarlos. Para el secreto:

```bash
openssl rand -hex 32
```

Después, la base:

```bash
docker compose -f infra/docker-compose.dev.yml up -d
```

La primera vez, el contenedor corre solo el script que crea el rol y el usuario
`app`. Sólo pasa con el volumen vacío: si alguna vez cambiás los privilegios del
rol, hay que borrar el volumen para que se vuelva a aplicar.

El backend, desde la raíz del repo:

```bash
uv run --directory backend fastapi dev app/main.py
```

Y el panel, **desde `frontend/`**:

```bash
pnpm install
```

```bash
pnpm dev
```

Panel en `http://localhost:3000`, API en `http://localhost:8000/docs`.

### Los tests, que es lo que más vas a correr

```bash
uv run --directory backend pytest -q
```

```bash
uv run --directory agente pytest -q
```

### Qué le falta a esta máquina

El agente sabe responderlo solo. Marca en rojo lo que hay que resolver y `n/a`
lo que no aplica acá:

```bash
uv run --directory agente python -m agente.main --diagnostico
```

Paso a paso completo en [`docs/04-AGENTE.md`](docs/04-AGENTE.md) §11.

## Qué hay acá

| Carpeta | Qué va |
|---|---|
| `backend/` | API FastAPI. La lógica de negocio vive acá y en ningún otro lado |
| `frontend/` | El panel, en Next.js 15 |
| `agente/` | Lo que corre en la Mac del vendedor |
| `infra/` | Compose local y despliegue |
| `docs/` | Documentación del proyecto |
| `referencia/` | El MVP fase 1, congelado. **No se importa nada desde ahí** |

## Antes de escribir la primera línea

Leé [`docs/03-REGLAS.md`](docs/03-REGLAS.md). Es corto, y describe los límites que el sistema no
puede cruzar. Después, [`docs/00-INDICE.md`](docs/00-INDICE.md) te dice en qué orden leer el resto.

## A quién le puede escribir el sistema

A los números que estén en `configuracion.destinos_permitidos`, y a nadie más. Se verifica en el
backend al encolar y otra vez en el agente antes de escribir.

**Mientras esa lista tenga sólo los números de prueba, es técnicamente imposible que un cliente
real reciba un mensaje.** Abrirla es un acto deliberado que queda registrado en auditoría. Es la
regla R4, y reemplaza a la regla anterior de que el código de envío no existiera en el repositorio.
