import { readFileSync } from 'node:fs';
import { connect, safeError } from './connection.mjs';
const pool = await connect();
try {
  const existing = await pool.request().query("SELECT COUNT(*) n FROM sys.tables WHERE schema_id=SCHEMA_ID('statsbomb')");
  if (existing.recordset[0].n) throw new Error('Schema is already installed; this script never overwrites tables.');
  const batches = readFileSync(new URL('./schema.sql', import.meta.url), 'utf8').split(/^GO\s*$/mi).filter(x=>x.trim());
  // Transactional DDL: a failed installation leaves no partial schema.
  const transaction = pool.transaction();
  await transaction.begin();
  try {
    for (let i=0; i<batches.length; i++) {
      try { await transaction.request().batch(batches[i]); }
      catch (e) { console.error('DDL batch', i + 1, batches[i].slice(0, 100)); throw e; }
    }
    await transaction.commit();
  } catch (e) { try { await transaction.rollback(); } catch {} throw e; }
  console.log(JSON.stringify({ status:'installed', batches:batches.length, tables:30, foreignKeys:43 }));
} catch(e) { console.error(JSON.stringify(safeError(e))); process.exitCode=1; }
finally { await pool.close(); }
