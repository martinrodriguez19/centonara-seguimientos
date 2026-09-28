import { describe, expect, it } from "vitest";

import {
  actividadDe,
  deHoy,
  dejadosHoy,
  dejadosPorDia,
  diaArgentino,
  juntarProblemas,
  motivosDeSalteo,
  porMaquina,
} from "@/lib/derivados";
import type { Alerta, Corrida, Maquina } from "@/lib/panel";

/**
 * Las cuentas del Panel v2 que no hace el backend.
 *
 * Son las que alimentan la barra de cada tarjeta, las estadísticas y el
 * contador de errores. Si una se equivoca, el panel muestra un número falso con
 * la misma seguridad que uno verdadero — por eso se prueban sin pantalla.
 */

const AHORA = new Date("2026-09-28T20:30:00Z"); // 17:30 en Buenos Aires

function corrida(parcial: Partial<Corrida> & { creada_en: string }): Corrida {
  return {
    id: parcial.creada_en,
    tipo: "generacion",
    modo: "prueba",
    estado: "terminada",
    maquinas: ["mac-rocio"],
    jobs: { total: 1, pendientes: 0 },
    terminada: true,
    costo_usd: 1,
    tandas: [],
    ...parcial,
  };
}

const tanda = (maquina: string, dejados: number, extra: Partial<Corrida["tandas"][number]> = {}) => ({
  maquina,
  pedidos: dejados + 2,
  dejados,
  salteados: 2,
  motivos: { sin_tema: 1, campo_ocupado: 1 },
  fin: null,
  ...extra,
});

describe("el día es el de Buenos Aires, no el de UTC", () => {
  it("las 23:30 argentinas son el mismo día aunque en UTC ya sea mañana", () => {
    expect(diaArgentino("2026-09-29T02:30:00Z")).toBe("2026-09-28");
  });

  it("una corrida de las 22 argentinas cuenta para hoy", () => {
    const tarde = corrida({ creada_en: "2026-09-29T01:00:00Z", tandas: [tanda("mac-rocio", 5)] });
    const ayer = corrida({ creada_en: "2026-09-27T20:00:00Z", tandas: [tanda("mac-rocio", 9)] });
    const hoy = deHoy([tarde, ayer], new Date("2026-09-29T02:00:00Z"));
    expect(hoy).toEqual([tarde]);
  });
});

describe("dejadosHoy", () => {
  it("suma las tandas de hoy de esa máquina, en todas las corridas", () => {
    const corridas = [
      corrida({ creada_en: "2026-09-28T13:00:00Z", tandas: [tanda("mac-rocio", 4), tanda("mac-julian", 7)] }),
      corrida({ creada_en: "2026-09-28T20:00:00Z", tandas: [tanda("mac-rocio", 3), tanda("mac-rocio", 2)] }),
      corrida({ creada_en: "2026-09-27T20:00:00Z", tandas: [tanda("mac-rocio", 50)] }),
    ];
    expect(dejadosHoy(corridas, "mac-rocio", AHORA)).toBe(9);
    expect(dejadosHoy(corridas, "mac-julian", AHORA)).toBe(7);
  });

  it("una corrida sin tandas (el listado no las trae) cuenta cero, no rompe", () => {
    const sinTandas = { ...corrida({ creada_en: "2026-09-28T13:00:00Z" }), tandas: undefined } as unknown as Corrida;
    expect(dejadosHoy([sinTandas], "mac-rocio", AHORA)).toBe(0);
  });
});

describe("dejadosPorDia", () => {
  it("incluye los días sin corridas en cero", () => {
    const serie = dejadosPorDia(
      [corrida({ creada_en: "2026-09-26T20:00:00Z", tandas: [tanda("mac-rocio", 6)] })],
      3,
      AHORA,
    );
    expect(serie).toEqual([
      { dia: "2026-09-26", valor: 6 },
      { dia: "2026-09-27", valor: 0 },
      { dia: "2026-09-28", valor: 0 },
    ]);
  });
});

describe("actividadDe y porMaquina", () => {
  const corridas = [
    corrida({
      creada_en: "2026-09-28T20:00:00Z",
      tandas: [
        tanda("mac-rocio", 4),
        tanda("mac-rocio", 3, { corte: "tope_diario_borradores", error: { codigo: "TIMEOUT", motivo: null } }),
        tanda("mac-julian", 8),
      ],
    }),
  ];

  it("junta las tandas de una máquina en una fila por corrida", () => {
    const [fila] = actividadDe(corridas, "mac-rocio");
    expect(fila.tandas).toBe(2);
    expect(fila.dejados).toBe(7);
    expect(fila.motivos).toEqual({ sin_tema: 2, campo_ocupado: 2 });
    expect(fila.corte).toBe("tope_diario_borradores");
    expect(fila.error?.codigo).toBe("TIMEOUT");
  });

  it("ordena las máquinas de más a menos dejados y cuenta las tandas con error", () => {
    expect(porMaquina(corridas).map((f) => [f.maquina, f.dejados, f.conError])).toEqual([
      ["mac-julian", 8, 0],
      ["mac-rocio", 7, 1],
    ]);
  });

  it("suma los motivos de salteo de todas las tandas", () => {
    expect(motivosDeSalteo(corridas)).toEqual([
      ["sin_tema", 3],
      ["campo_ocupado", 3],
    ]);
  });
});

describe("juntarProblemas", () => {
  const maquina = (parcial: Partial<Maquina>): Maquina => ({
    maquina: "mac-rocio",
    nombre: "Rocío",
    activo: true,
    pausada: false,
    online: true,
    ultimo_latido: AHORA.toISOString(),
    puede_enviar: true,
    chequeos_fallando: [],
    diagnostico: {},
    version_agente: null,
    version_esperada: null,
    actualizada: null,
    modo_agente: "operativo",
    tope_diario: 20,
    ...parcial,
  });
  const alerta = (parcial: Partial<Alerta>): Alerta => ({
    nivel: "aviso",
    codigo: "x",
    titulo: "t",
    detalle: "d",
    accion: "a",
    corrida_id: null,
    maquina: null,
    ...parcial,
  });

  it("pone las urgentes primero", () => {
    const lista = juntarProblemas([alerta({ codigo: "a" }), alerta({ codigo: "b", nivel: "urgente" })], []);
    expect(lista.map((p) => p.codigo)).toEqual(["b", "a"]);
  });

  it("suma lo que la tarjeta mostraba en grande: sin consentimiento y simulado", () => {
    const lista = juntarProblemas([], [maquina({ puede_enviar: false, modo_agente: "simulado" })]);
    expect(lista.map((p) => [p.codigo, p.maquina])).toEqual([
      ["sin_consentimiento", "mac-rocio"],
      ["modo_simulado", "mac-rocio"],
    ]);
  });

  it("una Mac apagada sin trabajo esperando no es un problema", () => {
    // El backend no alerta por eso ("una Mac apagada no es noticia"), y el
    // panel tampoco: sería justo el ruido que el Panel v2 vino a sacar.
    expect(juntarProblemas([], [maquina({ online: false })])).toEqual([]);
  });

  it("la firma cambia si cambia el detalle: un 'Ya lo vi' no tapa un problema nuevo", () => {
    const [antes] = juntarProblemas([alerta({ detalle: "3 envíos fallaron" })], []);
    const [despues] = juntarProblemas([alerta({ detalle: "5 envíos fallaron" })], []);
    expect(antes.firma).not.toBe(despues.firma);
  });
});
