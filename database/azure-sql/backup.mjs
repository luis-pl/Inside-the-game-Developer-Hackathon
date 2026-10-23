import { mkdirSync, createWriteStream, writeFileSync, existsSync } from 'node:fs';
import { createGzip } from 'node:zlib';
import { pipeline } from 'node:stream/promises';
import { connect, model } from './connection.mjs';
const label=process.argv[2]??'before-v2';
if(!/^before-v[0-9]+(?:-[a-z]+)*$/.test(label))throw new Error('Invalid backup label');
const target=new URL(`./backups/${label}/`,import.meta.url);
mkdirSync(target,{recursive:true});
if(existsSync(new URL('manifest.json',target))) throw new Error('Backup already exists; refusing to overwrite it.');
const pool=await connect(),manifest={createdAt:new Date().toISOString(),format:'gzip JSON Lines; one object per row',tables:{}};
try {
 for(const t of model.tables) {
  const path=new URL(t.name+'.jsonl.gz',target),zip=createGzip(),output=createWriteStream(path,{flags:'wx'});
  const writing=pipeline(zip,output),request=pool.request();request.stream=true;
  let count=0;
  await new Promise((resolve,reject)=>{
   request.on('row',row=>{count++;if(!zip.write(JSON.stringify(row)+'\n'))request.pause();});
   zip.on('drain',()=>request.resume());
   request.on('error',reject);
   request.on('done',resolve);
   request.query('SELECT * FROM statsbomb.['+t.name+']');
  });
  zip.end();await writing;
  manifest.tables[t.name]={file:t.name+'.jsonl.gz',rows:count};
 }
 writeFileSync(new URL('manifest.json',target),JSON.stringify(manifest,null,2)+'\n');
 console.log(JSON.stringify({backup:`backups/${label}`,tables:Object.keys(manifest.tables).length,rows:Object.values(manifest.tables).reduce((s,t)=>s+t.rows,0)}));
} finally {await pool.close();}
