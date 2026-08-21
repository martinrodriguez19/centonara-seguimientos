"""Normalización de números de teléfono a E.164.

Es una función chica con consecuencias grandes. Se usa en dos lugares donde un
error cuesta caro:

- **Anti-duplicado.** Si el mismo contacto normaliza distinto en dos corridas,
  recibe dos mensajes.
- **Verificación de identidad** (regla R1). Antes de escribir, el agente lee el
  número del chat abierto y lo compara con éste. Un falso negativo aborta un
  envío correcto; un falso positivo escribe en el chat equivocado.

Sólo Argentina. El día que haga falta otro país se agrega su tabla, no se
inventa una regla general: los planes de numeración no se parecen entre sí.
"""

from __future__ import annotations

import re

# Prefijo internacional de Argentina.
PAIS = "54"

# El "9" que va entre el país y el área en los celulares, y el "15" que se marca
# en las llamadas locales. Los dos sobran en E.164 y los dos aparecen en lo que
# la gente escribe.
MOVIL = "9"
LOCAL = "15"

# Área + abonado siempre suman diez dígitos en Argentina.
LARGO_NACIONAL = 10

# Códigos de área. Se prueban de más largo a más corto: 2966 (Río Gallegos) y
# 296 no existen los dos, pero 3446 y 344 sí se confundirían si se probara al
# revés.
#
# No es la tabla completa del ENACOM: son las áreas donde el cliente tiene
# clientes, más las capitales. Un número de un área que no esté acá se rechaza
# en vez de normalizarse mal — que es lo correcto: preferimos no mandar el
# mensaje antes que mandarlo a otro (R2).
# fmt: off
AREAS: frozenset[str] = frozenset(
    {
        # 2 dígitos — AMBA
        "11",
        # 3 dígitos — capitales y ciudades grandes
        "220", "221", "223", "230", "236", "237", "249", "260", "261", "262",
        "263", "264", "266", "280", "291", "294", "297", "299", "336", "341",
        "342", "343", "345", "348", "351", "353", "358", "362", "364", "370",
        "376", "379", "380", "381", "383", "385", "387", "388",
        # 4 dígitos — interior
        "2202", "2223", "2225", "2226", "2227", "2229", "2241", "2242", "2243", "2244",
        "2245", "2246", "2252", "2254", "2255", "2257", "2261", "2264", "2266", "2267",
        "2268", "2271", "2272", "2273", "2274", "2281", "2283", "2284", "2285", "2286",
        "2291", "2292", "2296", "2297", "2302", "2314", "2316", "2317", "2320", "2323",
        "2325", "2326", "2331", "2333", "2334", "2335", "2337", "2338", "2342", "2343",
        "2344", "2345", "2346", "2352", "2353", "2354", "2355", "2356", "2357", "2358",
        "2392", "2393", "2394", "2395", "2396", "2473", "2474", "2475", "2477", "2478",
        "2622", "2624", "2625", "2626", "2646", "2647", "2648", "2651", "2652", "2655",
        "2656", "2657", "2658", "2901", "2902", "2903", "2920", "2921", "2922", "2923",
        "2924", "2925", "2926", "2927", "2928", "2929", "2931", "2932", "2933", "2934",
        "2935", "2936", "2940", "2942", "2945", "2946", "2948", "2952", "2953", "2954",
        "2962", "2963", "2964", "2966", "2972", "2982", "2983", "3327", "3329", "3382",
        "3387", "3388", "3400", "3401", "3402", "3404", "3405", "3406", "3407", "3408",
        "3409", "3435", "3436", "3437", "3438", "3442", "3444", "3445", "3446", "3447",
        "3454", "3455", "3456", "3458", "3460", "3462", "3463", "3464", "3465", "3466",
        "3467", "3468", "3469", "3471", "3472", "3476", "3482", "3483", "3487", "3489",
        "3491", "3492", "3493", "3496", "3497", "3498", "3521", "3522", "3524", "3525",
        "3532", "3533", "3537", "3541", "3542", "3543", "3544", "3546", "3547", "3548",
        "3549", "3562", "3563", "3564", "3571", "3572", "3573", "3574", "3575", "3576",
        "3582", "3583", "3584", "3585", "3711", "3715", "3716", "3718", "3721", "3725",
        "3731", "3734", "3735", "3741", "3743", "3751", "3754", "3755", "3756", "3757",
        "3758", "3772", "3773", "3774", "3775", "3777", "3781", "3782", "3786", "3821",
        "3825", "3826", "3827", "3832", "3835", "3837", "3838", "3841", "3843", "3844",
        "3845", "3846", "3854", "3855", "3856", "3857", "3858", "3861", "3862", "3863",
        "3865", "3867", "3868", "3869", "3873", "3876", "3877", "3878", "3885", "3886",
        "3887", "3888", "3891", "3892", "3894",
    }
)
# fmt: on

_LARGOS_AREA = (4, 3, 2)

_SOLO_DIGITOS = re.compile(r"\D")


class NumeroInvalido(ValueError):
    """No se pudo normalizar. Se propaga: nunca se devuelve un número dudoso.

    `motivo` es un código estable, para poder distinguir en el registro por qué
    falló sin parsear un mensaje en castellano.
    """

    def __init__(self, motivo: str, detalle: str = "") -> None:
        self.motivo = motivo
        self.detalle = detalle
        super().__init__(f"{motivo}: {detalle}" if detalle else motivo)


def normalizar(crudo: str | None) -> str:
    """Devuelve el número en E.164 (`+549XXXXXXXXXX`) o lanza `NumeroInvalido`.

    Acepta lo que la gente escribe de verdad:

        >>> normalizar("11 4440-5036")
        '+5491144405036'
        >>> normalizar("+54 11 4440 5036")
        '+5491144405036'
        >>> normalizar("0111544405036")
        '+5491144405036'
        >>> normalizar("+549 11 4440-5036")
        '+5491144405036'
        >>> normalizar("1544405036")
        '+5491144405036'

    Todos los celulares argentinos salen con el `9`, que es lo que usa WhatsApp.
    """
    if crudo is None:
        raise NumeroInvalido("vacio")

    tenia_mas = crudo.strip().startswith("+")
    digitos = _SOLO_DIGITOS.sub("", crudo)

    if not digitos:
        raise NumeroInvalido("vacio", crudo)

    # Un `+` seguido de algo que no es 54 es otro país. No lo tocamos: mejor
    # rechazarlo que normalizarlo con reglas argentinas y acertar por azar.
    if tenia_mas and not digitos.startswith(PAIS):
        raise NumeroInvalido("pais_no_soportado", crudo)

    nacional = _quitar_prefijos(digitos)
    nacional = _quitar_quince(nacional)

    if len(nacional) != LARGO_NACIONAL:
        raise NumeroInvalido("largo_invalido", f"{crudo} → {nacional} ({len(nacional)} dígitos)")

    if _area_de(nacional) is None:
        raise NumeroInvalido("area_desconocida", f"{crudo} → {nacional}")

    return f"+{PAIS}{MOVIL}{nacional}"


def _quitar_prefijos(digitos: str) -> str:
    """Saca el código de país, el 0 de larga distancia y el 9 de celular.

    El orden importa y no es intercambiable: `0111544405036` empieza con el 0
    nacional, y `5491144405036` con el país. Si se probara el 9 antes que el
    país, `9...` de un número que empieza con área inexistente se comería un
    dígito bueno.
    """
    if digitos.startswith(PAIS) and len(digitos) > LARGO_NACIONAL:
        digitos = digitos[len(PAIS) :]

    # El 0 nunca es parte del número: es el prefijo de larga distancia.
    while digitos.startswith("0"):
        digitos = digitos[1:]

    # El 9 sólo sobra si lo que queda sigue siendo un número nacional completo.
    # Ningún código de área argentino empieza con 9, así que no hay ambigüedad,
    # pero igual se verifica el largo antes de tocar nada.
    if digitos.startswith(MOVIL) and len(digitos) > LARGO_NACIONAL:
        digitos = digitos[len(MOVIL) :]

    return digitos


def _quitar_quince(nacional: str) -> str:
    """Saca el `15` que va entre el código de área y el abonado.

    `11 15 4440-5036` es cómo se marca localmente y es cómo la gente lo escribe.
    En E.164 no existe.

    Se prueba área por área en vez de buscar `15` en cualquier lado: hay números
    que **empiezan** con 15 legítimamente, y borrarlo ahí rompería un número
    válido.
    """
    # Ya tiene el largo correcto Y un área válida: no hay nada que sacar.
    # Las dos condiciones, no una: `1544405036` mide diez dígitos y aun así le
    # sobra el 15 — es un celular de AMBA anotado como se marca desde AMBA.
    if len(nacional) == LARGO_NACIONAL and _area_de(nacional) is not None:
        return nacional

    for largo in _LARGOS_AREA:
        area, resto = nacional[:largo], nacional[largo:]
        if area in AREAS and resto.startswith(LOCAL):
            candidato = area + resto[len(LOCAL) :]
            if len(candidato) == LARGO_NACIONAL:
                return candidato

    # `1544405036`: el 15 adelante, sin área. Es el celular de alguien de AMBA
    # anotado como se marca desde AMBA. Se asume 11, que es lo que significa.
    if nacional.startswith(LOCAL) and len(nacional) == LARGO_NACIONAL:
        return "11" + nacional[len(LOCAL) :]

    return nacional


def _area_de(nacional: str) -> str | None:
    """El código de área, probando de más largo a más corto. `None` si no está."""
    for largo in _LARGOS_AREA:
        if nacional[:largo] in AREAS:
            return nacional[:largo]
    return None


def son_el_mismo(uno: str | None, otro: str | None) -> bool:
    """¿Los dos números son el mismo contacto?

    Es lo que usa la verificación de identidad antes de escribir (R1) y el
    anti-duplicado. **Falla cerrado**: si alguno de los dos no se puede
    normalizar, la respuesta es que no son el mismo — nunca se escribe "por las
    dudas".
    """
    try:
        return normalizar(uno) == normalizar(otro)
    except NumeroInvalido:
        return False
