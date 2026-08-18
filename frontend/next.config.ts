import path from "node:path";
import { fileURLToPath } from "node:url";

import type { NextConfig } from "next";

const aca = path.dirname(fileURLToPath(import.meta.url));

const nextConfig: NextConfig = {
  // Next busca la raíz del workspace hacia arriba y, en el monorepo, encuentra
  // lockfiles de otros lados (incluso fuera del repo). Si adivina mal, el
  // trazado de archivos del build se lleva lo que no es. Se lo decimos.
  outputFileTracingRoot: aca,
};

export default nextConfig;
