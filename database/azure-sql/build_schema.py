"""Port the reviewed 30-table model to Azure SQL; no database connection."""
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).parent
model = json.loads((ROOT / 'model.json').read_text(encoding='utf-8'))
q = lambda value: '[' + value + ']'
table = lambda name: '[statsbomb].' + q(name)
types = {'int': 'int', 'bigint': 'bigint', 'uuid': 'uniqueidentifier',
         'boolean': 'bit', 'double precision': 'float(53)', 'jsonb': 'nvarchar(max)',
         'text': 'nvarchar(256)', 'timestamp': 'datetime2(6)', 'date': 'date', 'time': 'time(6)'}

def check(expr):
    # SQL Server's float type does not accept PostgreSQL NaN/Infinity values.
    expr = re.sub(r'"\w+"\s*[<>]\s*\'-?Infinity\'::float8', '1=1', expr)
    expr = re.sub(r'jsonb_typeof\("(\w+)"\)\s*=\s*\'object\'', r'ISJSON([\1], OBJECT)=1', expr)
    expr = re.sub(r'jsonb_typeof\("(\w+)"\)\s*=\s*\'array\'', r'ISJSON([\1], ARRAY)=1', expr)
    if 'jsonb_array_length' in expr:
        return None  # OPENJSON requires a trigger in T-SQL.
    expr = expr.replace('("position_status"=\'missing\') = ("sample_method"=\'missing\')',
                        '(("position_status"=\'missing\' AND "sample_method"=\'missing\') OR ("position_status"<>\'missing\' AND "sample_method"<>\'missing\'))')
    expr = expr.replace('NOT "is_on_pitch"', '"is_on_pitch"=0').replace('("is_on_pitch" AND', '("is_on_pitch"=1 AND')
    expr = expr.replace('=true', '=1').replace('=false', '=0')
    return re.sub(r'"(\w+)"', lambda m: q(m[1]), expr)

sql = ["-- Azure SQL / SQL Server. Fresh database only. Generated from model.json.",
       "SET XACT_ABORT ON;\nGO\nCREATE SCHEMA statsbomb;\nGO\nCREATE SCHEMA analytics;\nGO"]
sql.append("""
CREATE FUNCTION statsbomb.clock_ms(@clock nvarchar(32)) RETURNS bigint WITH SCHEMABINDING AS
BEGIN
 DECLARE @c int=CHARINDEX(':',@clock),@sec nvarchar(16),@hours nvarchar(32),@mins nvarchar(2);
 IF @c<3 RETURN NULL;
 SET @hours=LEFT(@clock,@c-1); SET @mins=SUBSTRING(@clock,@c+1,2); SET @sec=SUBSTRING(@clock,@c+4,16);
 IF SUBSTRING(@clock,@c+3,1)<>':' OR @hours COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9]%'
   OR @mins COLLATE Latin1_General_100_BIN2 NOT LIKE '[0-5][0-9]'
   OR LEFT(@sec,2) COLLATE Latin1_General_100_BIN2 NOT LIKE '[0-5][0-9]'
   OR LEN(@sec)<2 OR LEN(@sec)>9 RETURN NULL;
 IF LEN(@sec)>2 AND (SUBSTRING(@sec,3,1)<>'.' OR LEN(@sec)<4
   OR SUBSTRING(@sec,4,6) COLLATE Latin1_General_100_BIN2 LIKE '%[^0-9]%') RETURN NULL;
 IF TRY_CONVERT(bigint,@hours)>1000000000 RETURN NULL;
 RETURN TRY_CONVERT(bigint,@hours)*3600000+TRY_CONVERT(bigint,@mins)*60000
   +TRY_CONVERT(bigint,FLOOR(TRY_CONVERT(decimal(12,6),@sec)*1000));
END;
GO
""")
for t in model['tables']:
    name = t['name']
    rows = []
    for f in t['fields']:
        if f.get('generated'):
            # Relative clock; unlimited hour component (nvarchar rather than SQL time).
            rows.append("[period_time_ms] AS statsbomb.clock_ms([timestamp]) PERSISTED")
            continue
        datatype = types[f['type']]
        if f['name'] == 'timestamp': datatype = 'nvarchar(32)'
        if f['name'] in ('from_time', 'to_time', 'time'): datatype = 'nvarchar(32)'
        default = model.get('defaults', {}).get(name, {}).get(f['name'], f.get('default'))
        line = q(f['name']) + ' ' + datatype + (' NOT NULL' if f['required'] else ' NULL')
        if default is not None:
            default = str(default).replace("::jsonb", '').replace('true', '1').replace('false', '0')
            line += ' DEFAULT (' + default + ')'
        rows.append(line)
    if name == 'matches':
        rows += ["[data_status] nvarchar(16) NOT NULL DEFAULT 'loading'", "CHECK ([data_status] IN ('loading','ready'))"]
    rows.append('CONSTRAINT ' + q('pk_' + name) + ' PRIMARY KEY (' + ','.join(q(f['name']) for f in t['fields'] if f['pk']) + ')')
    for i, cols in enumerate(model['unique'].get(name, [])):
        if name == 'tracking_player_positions' and 'on_pitch_slot' in cols:
            continue  # SQL Server UNIQUE treats NULL as a value; use filtered unique index below.
        rows.append('CONSTRAINT ' + q('uq_' + name + '_' + str(i)) + ' UNIQUE (' + ','.join(map(q, cols)) + ')')
    for i, expr in enumerate(model['checks'].get(name, [])):
        expr = check(expr)
        if expr: rows.append('CONSTRAINT ' + q('ck_' + name + '_' + str(i)) + ' CHECK (' + expr + ')')
    if name == 'events':
        rows.append("CONSTRAINT ck_event_clock CHECK ([period_time_ms] IS NOT NULL AND [period_time_ms]>=0)")
    sql.append('CREATE TABLE ' + table(name) + '(\n  ' + ',\n  '.join(rows) + '\n);\nGO')

for i, (child, cols, parent, pcols) in enumerate(model['refs']):
    sql.append('ALTER TABLE ' + table(child) + ' ADD CONSTRAINT ' + q('fk_' + str(i) + '_' + child) + ' FOREIGN KEY (' + ','.join(map(q, cols)) + ') REFERENCES ' + table(parent) + '(' + ','.join(map(q, pcols)) + ');')
    keys = [[f['name'] for f in next(t for t in model['tables'] if t['name']==child)['fields'] if f['pk']]] + model['unique'].get(child, [])
    if not any(k[:len(cols)]==cols for k in keys):
        sql.append('CREATE INDEX ' + q('ix_fk_' + str(i)) + ' ON ' + table(child) + '(' + ','.join(map(q, cols)) + ');')
sql += ["CREATE UNIQUE INDEX uq_active_slot ON statsbomb.tracking_player_positions(run_id,period,frame_index,team_id,on_pitch_slot) WHERE on_pitch_slot IS NOT NULL;",
        "CREATE INDEX ix_events_match_clock ON statsbomb.events(match_id,period,period_time_ms) INCLUDE(type_id,team_id,player_id,location_x,location_y);",
        "CREATE INDEX ix_positions_player ON statsbomb.tracking_player_positions(match_id,player_id,period,frame_index) INCLUDE(x_m,y_m,position_status);", 'GO']
sql.append((ROOT/'quality-rules.sql').read_text(encoding='utf-8'))

# SQL Server has immediate FK/CHECK constraints, not deferred constraint triggers.
# Publish only a complete match, and seal the published graph against mutation.
sql.append("""
CREATE PROCEDURE statsbomb.validate_match @match_id int AS
BEGIN
 SET NOCOUNT ON;
 IF (SELECT COUNT(*) FROM statsbomb.match_teams WHERE match_id=@match_id)<>2
   OR NOT EXISTS(SELECT 1 FROM statsbomb.match_teams WHERE match_id=@match_id AND side='home')
   OR NOT EXISTS(SELECT 1 FROM statsbomb.match_teams WHERE match_id=@match_id AND side='away')
   THROW 51001,'A match needs exactly one home and one away team.',1;
 IF EXISTS(SELECT 1 FROM statsbomb.events e WHERE match_id=@match_id AND
   ((type_id=30 AND NOT EXISTS(SELECT 1 FROM statsbomb.event_passes d WHERE d.event_id=e.event_id))
   OR (type_id=16 AND NOT EXISTS(SELECT 1 FROM statsbomb.event_shots d WHERE d.event_id=e.event_id))
   OR (type_id IN (35,36) AND NOT EXISTS(SELECT 1 FROM statsbomb.event_tactics d WHERE d.event_id=e.event_id))))
   THROW 51002,'An event is missing its required detail row.',1;
 IF EXISTS(SELECT 1 FROM statsbomb.tracking_frames f JOIN statsbomb.tracking_periods p
   ON p.run_id=f.run_id AND p.period=f.period WHERE f.match_id=@match_id AND f.period_time_ms>p.duration_ms)
   THROW 51003,'A tracking frame lies outside its period.',1;
 IF EXISTS(SELECT 1 FROM statsbomb.event_tracking_links l
   JOIN statsbomb.events e ON e.event_id=l.event_id
   JOIN statsbomb.tracking_frames f ON f.run_id=l.run_id AND f.period=l.period AND f.frame_index=l.frame_index
   JOIN statsbomb.tracking_runs r ON r.run_id=l.run_id
   JOIN statsbomb.tracking_periods p ON p.run_id=l.run_id AND p.period=l.period
   WHERE l.match_id=@match_id AND (e.period_time_ms>p.duration_ms
     OR ABS(e.period_time_ms-f.period_time_ms)>r.max_event_offset_ms
     OR (l.alignment_method='exact' AND e.period_time_ms<>f.period_time_ms)))
   THROW 51004,'Event and tracking clocks are not aligned.',1;
 EXEC statsbomb.validate_semantics @match_id;
END;
GO
CREATE TRIGGER statsbomb.seal_match ON statsbomb.matches AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 IF EXISTS(SELECT 1 FROM deleted WHERE data_status='ready')
   THROW 51005,'Published matches are immutable. Import a new version.',1;
 DECLARE @id int;
 DECLARE ready_matches CURSOR LOCAL FAST_FORWARD FOR SELECT match_id FROM inserted WHERE data_status='ready';
 OPEN ready_matches;
 FETCH NEXT FROM ready_matches INTO @id;
 WHILE @@FETCH_STATUS=0
 BEGIN
   EXEC statsbomb.validate_match @id;
   FETCH NEXT FROM ready_matches INTO @id;
 END;
 CLOSE ready_matches; DEALLOCATE ready_matches;
END;
GO
CREATE PROCEDURE statsbomb.publish_match @match_id int AS
BEGIN
 SET NOCOUNT ON; SET XACT_ABORT ON;
 BEGIN TRY
   BEGIN TRANSACTION;
   DECLARE @state nvarchar(16);
   SELECT @state=data_status FROM statsbomb.matches WITH (UPDLOCK,HOLDLOCK) WHERE match_id=@match_id;
   IF @state IS NULL THROW 51006,'Unknown match.',1;
   IF @state<>'loading' THROW 51007,'Match already published.',1;
   UPDATE statsbomb.matches SET data_status='ready' WHERE match_id=@match_id;
   COMMIT;
 END TRY
 BEGIN CATCH
   IF XACT_STATE()<>0 ROLLBACK;
   THROW;
 END CATCH;
END;
GO
""")
for t in model['tables']:
    name = t['name']
    if name=='matches': continue
    cols = [f['name'] for f in t['fields']]
    if 'match_id' in cols:
        context = 'SELECT match_id FROM inserted UNION SELECT match_id FROM deleted'
    elif name=='frame_360_players':
        context = 'SELECT f.match_id FROM statsbomb.frames_360 f JOIN (SELECT event_id FROM inserted UNION SELECT event_id FROM deleted) x ON x.event_id=f.event_id'
    else: continue
    sql.append(f"""CREATE TRIGGER statsbomb.{q('seal_' + name)} ON {table(name)} AFTER INSERT,UPDATE,DELETE AS
BEGIN
 SET NOCOUNT ON;
 -- HOLDLOCK serializes imports against concurrent publication.
 IF EXISTS(SELECT 1 FROM statsbomb.matches m WITH (HOLDLOCK) JOIN ({context}) x ON m.match_id=x.match_id WHERE m.data_status='ready')
   THROW 51008,'Rows of published matches are immutable.',1;
END;
GO""")
for name in ['tracking_runs','tracking_periods']:
    sql.append(f"""CREATE TRIGGER statsbomb.{q('version_' + name)} ON {table(name)} AFTER UPDATE AS
BEGIN
 IF EXISTS(SELECT 1 FROM inserted) THROW 51009,'Create a new run instead of editing tracking metadata.',1;
END;
GO""")
sql.append("""
CREATE TRIGGER statsbomb.valid_visible_area ON statsbomb.frames_360 AFTER INSERT,UPDATE AS
BEGIN
 IF EXISTS(SELECT 1 FROM inserted i WHERE i.visible_area IS NOT NULL AND
   ((SELECT COUNT(*) FROM OPENJSON(i.visible_area)) % 2 <> 0
    OR EXISTS(SELECT 1 FROM OPENJSON(i.visible_area) WHERE type<>2)))
   THROW 51010,'visible_area must contain numeric coordinate pairs.',1;
END;
GO
""")
for t in model['tables']:
    name=t['name']; cols=[f['name'] for f in t['fields']]
    if name=='matches': query="SELECT * FROM statsbomb.matches WHERE data_status='ready'"
    elif 'match_id' in cols: query=f"SELECT d.* FROM {table(name)} d JOIN statsbomb.matches m ON m.match_id=d.match_id WHERE m.data_status='ready'"
    elif name=='frame_360_players': query="SELECT d.* FROM statsbomb.frame_360_players d JOIN analytics.frames_360 f ON f.event_id=d.event_id"
    else: query=f'SELECT * FROM {table(name)}'
    sql.append(f'CREATE VIEW analytics.{q(name)} AS {query};\nGO')
sql.append("""
CREATE VIEW analytics.shots AS
 SELECT e.match_id,e.event_id,e.period,e.period_time_ms,e.minute,e.second,e.team_id,e.player_id,
 e.location_x,e.location_y,s.statsbomb_xg AS xg,TRY_CONVERT(int,JSON_VALUE(s.outcome,'$.id')) AS outcome_id,
 JSON_VALUE(s.outcome,'$.name') AS outcome_name,
 CONVERT(bit,CASE WHEN TRY_CONVERT(int,JSON_VALUE(s.outcome,'$.id')) IN (97,100,116) THEN 1 ELSE 0 END) AS is_on_target,
 CONVERT(bit,CASE WHEN JSON_VALUE(m.raw_payload,'$.is_synthetic')='true' THEN 1 ELSE 0 END) AS is_synthetic
 FROM analytics.events e JOIN analytics.event_shots s ON s.event_id=e.event_id
 JOIN analytics.matches m ON m.match_id=e.match_id;
GO
CREATE ROLE football_reader;
GRANT SELECT ON SCHEMA::analytics TO football_reader;
GO
""")
(ROOT/'schema.sql').write_text('\n\n'.join(sql),encoding='utf-8')
print(f"Generated schema.sql: {len(model['tables'])} tables, {len(model['refs'])} foreign keys")
