import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

/**
 * Las paletas de Tailwind que NO se usan en este panel.
 *
 * Existe porque ya pasó: como no había colores de estado en `globals.css`, cada
 * componente que necesitaba señalar algo se inventaba la clase en el momento.
 * Quedaron 41 usos sueltos de `amber-500/40`, `bg-amber-500/10`,
 * `text-amber-800 dark:text-amber-300` repartidos por seis componentes, cada
 * uno con su propia intensidad — y dos pantallas nunca se veían igual porque
 * nada las obligaba.
 *
 * Ahora los estados salen de tokens (`ok`, `atencion`, `critico`) y de
 * `components/ui/estado.tsx`. Este guard es lo que evita que la costumbre
 * vuelva: el que necesite un color nuevo tiene que agregarlo al sistema, que es
 * exactamente la conversación que hay que tener.
 *
 * ⚠️ Un check que sólo verificaste que pasa, no sabés si sirve. Para probar que
 * este agarra algo, poné `className="text-amber-500"` en cualquier componente y
 * corré `pnpm lint`: tiene que fallar.
 */
const PALETAS_PROHIBIDAS =
  "slate|gray|zinc|neutral|stone|red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose";

const CLASE_DE_COLOR = new RegExp(
  `\\b(?:text|bg|border|ring|from|via|to|decoration|outline|shadow|fill|stroke|divide|accent|caret)-(?:${PALETAS_PROHIBIDAS})-\\d{2,3}\\b`,
);

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [
      "node_modules/**",
      ".next/**",
      "out/**",
      "build/**",
      "next-env.d.ts",
      // Mientras las dependencias de test no estén en el lockfile, lintearlos
      // sería quejarse de imports que todavía no se pueden instalar.
      // Ver tests/README.md.
      "tests/**",
      "e2e/**",
    ],
  },
  {
    files: ["app/**/*.tsx", "components/**/*.tsx"],
    // `components/ui/` de shadcn queda afuera: son componentes traídos de
    // afuera y se actualizan copiándolos de nuevo. Reescribirlos para que pasen
    // este guard significaría rehacer el trabajo en cada actualización.
    ignores: ["components/ui/badge.tsx", "components/ui/button.tsx", "components/ui/card.tsx"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector: `Literal[value=/${CLASE_DE_COLOR.source}/]`,
          message:
            "Color literal de Tailwind. Los estados salen de los tokens de globals.css " +
            "(ok / atencion / critico) y se aplican con <Pildora> o <Aviso> de components/ui/estado.tsx. " +
            "Si hace falta un color que no está, se agrega al sistema.",
        },
        {
          selector: `TemplateElement[value.raw=/${CLASE_DE_COLOR.source}/]`,
          message:
            "Color literal de Tailwind dentro de un template. Ver components/ui/estado.tsx.",
        },
      ],
    },
  },
];

export default eslintConfig;
