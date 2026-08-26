// Crea el usuario con el que se conecta el backend, y su rol.
//
// Lo corre Mongo una sola vez, cuando el volumen está vacío. En Atlas el
// equivalente se hace desde la consola; el contenido es el mismo y está en
// docs/RUNBOOK-auditoria.md.
//
// ⚠️ LO IMPORTANTE DE ESTE ARCHIVO: el rol NO otorga `update` ni `remove` sobre
// `auditoria`. Eso es lo que hace que el registro sea inmutable de verdad y no
// por buena voluntad del código.
//
// MongoDB no tiene forma de PROHIBIR una acción: los roles sólo otorgan. Por eso
// hay que enumerar colección por colección en vez de dar `readWrite` sobre la
// base entera — `readWrite` incluiría `update` sobre auditoría y no habría manera
// de sacárselo después.

const BASE = "seguimiento";

const ESCRITURA = [
  "find",
  "insert",
  "update",
  "remove",
  "createIndex",
  "createCollection",
  "listIndexes",
  "listCollections",
  "dropCollection",
];

// Sólo leer y agregar. Sin `update`, sin `remove`.
const SOLO_AGREGAR = ["find", "insert", "createIndex", "listIndexes", "listCollections"];

// `telefonos` es la memoria de números que resolvió el agente (D27): nombre del
// contacto -> número real leído del panel. Se pisa en cada resolución nueva, así
// que necesita escritura como el resto.
const CON_ESCRITURA = [
  "vendedores",
  "corridas",
  "mensajes",
  "jobs",
  "configuracion",
  "telefonos",
];

const privilegios = CON_ESCRITURA.map((coleccion) => ({
  resource: { db: BASE, collection: coleccion },
  actions: ESCRITURA,
}));

privilegios.push({
  resource: { db: BASE, collection: "auditoria" },
  actions: SOLO_AGREGAR,
});

// Para que el backend pueda listar colecciones y asegurar el esquema al arrancar.
privilegios.push({
  resource: { db: BASE, collection: "" },
  actions: ["listCollections", "createCollection"],
});

const db = new Mongo().getDB(BASE);

db.createRole({
  role: "app_seguimiento",
  privileges: privilegios,
  roles: [],
});

db.createUser({
  user: "app",
  pwd: "app-local",  // sólo local: en Atlas la genera la consola y va en MONGO_URL
  roles: [{ role: "app_seguimiento", db: BASE }],
});

print("rol app_seguimiento y usuario app creados en " + BASE);
