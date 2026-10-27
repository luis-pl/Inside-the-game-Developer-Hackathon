// Aplica (o revierte con --rollback) los alias de team-names.json en statsbomb.teams.
// Una sola transacción: si algún equipo no tiene el nombre esperado, no cambia nada.
import { readFileSync, writeFileSync } from 'node:fs';
import { connect, sql, safeError } from './connection.mjs';

const rollback = process.argv.includes('--rollback');
const { teams } = JSON.parse(readFileSync(new URL('./team-names.json', import.meta.url), 'utf8'));
const pool = await connect();
const tx = new sql.Transaction(pool);
const report = { at: new Date().toISOString(), mode: rollback ? 'rollback' : 'apply', updated: 0, unchanged: 0 };
try {
  await tx.begin();
  for (const t of teams) {
    const [from, to] = rollback ? [t.team_name, t.previous_name] : [t.previous_name, t.team_name];
    const current = (await new sql.Request(tx).input('id', sql.Int, t.team_id)
      .query('SELECT team_name FROM statsbomb.teams WITH (UPDLOCK) WHERE team_id=@id')).recordset[0]?.team_name;
    if (current === to) { report.unchanged++; continue; }
    if (current !== from) throw new Error(`team ${t.team_id}: unexpected name ${JSON.stringify(current)}`);
    await new sql.Request(tx).input('id', sql.Int, t.team_id).input('name', sql.NVarChar(256), to)
      .query('UPDATE statsbomb.teams SET team_name=@name WHERE team_id=@id');
    report.updated++;
  }
  await tx.commit();
} catch (error) {
  await tx.rollback().catch(() => {});
  report.error = safeError(error);
  process.exitCode = 1;
} finally {
  await pool.close();
}
writeFileSync(new URL('./rename-teams-report.json', import.meta.url), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report));
