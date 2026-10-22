import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { connect, sql } from './connection.mjs';
const pool=await connect();
try{
 for(const batch of readFileSync(new URL('./quality-rules.sql',import.meta.url),'utf8').split(/^GO\s*$/mi).filter(s=>s.trim()))await pool.request().batch(batch);
 // Correct the canonical yellow-card ID (7) in versions generated before the
 // final source-catalog cross-check. Preserve the old cells before changing them.
 const old=await pool.request().query("SELECT event_id,match_id,details FROM statsbomb.events WHERE type_id=22 AND JSON_VALUE(details,'$.foul_committed.card.id')='65' AND JSON_VALUE(details,'$.foul_committed.card.name')='Yellow Card'");
 const backup=new URL('./backups/before-v2/card-code-before-final-check.json',import.meta.url);
 if(old.recordset.length){
  if(existsSync(backup))throw new Error('Metadata backup already exists; review before repeating.');
  writeFileSync(backup,JSON.stringify(old.recordset,null,2)+'\n');
  for(const id of [...new Set(old.recordset.map(r=>r.match_id))]){
   const tx=pool.transaction();await tx.begin();
   try{
    await tx.request().input('id',sql.Int,id).batch(`
      DISABLE TRIGGER statsbomb.seal_match ON statsbomb.matches;
      UPDATE statsbomb.matches SET data_status='loading' WHERE match_id=@id;
      ENABLE TRIGGER statsbomb.seal_match ON statsbomb.matches;
      UPDATE statsbomb.events SET details=JSON_MODIFY(details,'$.foul_committed.card.id',7)
       WHERE match_id=@id AND type_id=22 AND JSON_VALUE(details,'$.foul_committed.card.id')='65';
      EXEC statsbomb.publish_match @match_id=@id;
    `);await tx.commit();
   }catch(e){try{await tx.rollback();}catch{}throw e;}
  }
 }
 console.log(JSON.stringify({semanticRules:'installed',correctedCardCodes:old.recordset.length}));
}finally{await pool.close();}
