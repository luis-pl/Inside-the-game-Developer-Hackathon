import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const require = createRequire(import.meta.url);
export const sql = require(process.env.SQL_DRIVER_PATH || 'mssql');
export const model = JSON.parse(readFileSync(new URL('./model.json', import.meta.url), 'utf8'));
export const deployment = JSON.parse(readFileSync(new URL('./deployment.json', import.meta.url), 'utf8'));

export async function connect() {
  const cli = process.env.AZURE_CLI_PATH || 'az';
  const args = ['account', 'get-access-token', '--resource', 'https://database.windows.net/', '--query', 'accessToken', '-o', 'tsv'];
  // The access token stays in memory and is never printed or written to a file.
  const token = (process.platform === 'win32' && cli.endsWith('.cmd')
    ? execFileSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', `& '${cli.replaceAll("'", "''")}' ${args.join(' ')}`], { encoding: 'utf8', windowsHide: true })
    : execFileSync(cli, args, { encoding: 'utf8', windowsHide: true })).trim();
  return new sql.ConnectionPool({
    server: deployment.server + '.database.windows.net', database: deployment.database,
    authentication: { type: 'azure-active-directory-access-token', options: { token } },
    options: { encrypt: true, trustServerCertificate: false, enableArithAbort: true },
    connectionTimeout: 90000, requestTimeout: 180000,
    pool: { min: 0, max: 2, idleTimeoutMillis: 10000 },
  }).connect();
}

export async function bulk(target, name, records) {
  if (!records.length) return;
  const def = model.tables.find(t => t.name === name);
  const fields = def.fields.filter(f => !f.generated);
  const data = new sql.Table(`statsbomb.${name}`);
  data.create = false;
  for (const f of fields) {
    let type = ({ int: sql.Int, bigint: sql.BigInt, uuid: sql.UniqueIdentifier, boolean: sql.Bit,
      'double precision': sql.Float, date: sql.Date, timestamp: sql.DateTime2(6), time: sql.Time(6),
      jsonb: sql.NVarChar(sql.MAX), text: sql.NVarChar(['timestamp', 'from_time', 'to_time', 'time'].includes(f.name) ? 32 : 256) })[f.type];
    data.columns.add(f.name, type, { nullable: !f.required });
  }
  for (const r of records) data.rows.add(...fields.map(f => {
    let v = r[f.name];
    if (v === undefined) {
      const d = model.defaults?.[name]?.[f.name] ?? f.default;
      if (d !== undefined) {
        if (d === 'true') v = true;
        else if (d === 'false') v = false;
        else if (String(d).startsWith("'")) v = String(d).replace(/::jsonb$/, '').slice(1, -1);
        else v = Number(d);
      }
    }
    if (v === undefined || v === null) return null;
    if (f.type === 'jsonb' && typeof v !== 'string') return JSON.stringify(v);
    if (['date', 'time', 'timestamp'].includes(f.type) && !(v instanceof Date)) return new Date(v);
    return v;
  }));
  await new sql.Request(target).bulk(data, { checkConstraints: true, fireTriggers: true, keepNulls: true, tableLock: false });
}

export function safeError(error) {
  // Avoid driver connection configuration or Azure token output in diagnostics.
  return { name: error.name, code: error.code, number: error.number, message: error.message };
}
