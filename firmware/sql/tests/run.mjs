// PGlite runs the actual PostgreSQL engine in WASM; no production connection.
import { PGlite } from './.runtime/node_modules/@electric-sql/pglite/dist/index.js';
import { readFile } from 'node:fs/promises';
const db = new PGlite();
let failed = false;
const read = async (name) => (await readFile(new URL(name, import.meta.url), 'utf8')).replace(/^\\set.*$/gm, '');
try {
  await db.exec(await read('fixture.sql'));
  if (!process.argv.includes('--red')) {
    await db.exec(await read('../frota.sql'));
    await db.exec(await read('../frota.sql'));
    await db.exec(await read('../exclusoes.sql'));
    await db.exec(await read('../exclusoes.sql'));
    await db.exec(await read('../mapa_ocorrencias.sql'));
    await db.exec(await read('../mapa_ocorrencias.sql'));
  }
  const results = await db.exec(await read('assertions.sql'));
  console.log(results.at(-1).rows);
  console.log((await db.exec(await read('mapa_ocorrencias.sql'))).at(-1).rows);
  console.log((await db.exec(await read('exclusoes.sql'))).at(-1).rows);
} catch (error) {
  console.error(`${error.code}: ${error.message}`);
  failed = true;
} finally {
  await db.close();
}
if (failed) process.exitCode = 1;
