-- Generado desde team-names.json. Equivalente a: node rename-teams.mjs --rollback
-- Una transacción; aborta si algún equipo no tiene el nombre esperado ni el final.
SET XACT_ABORT ON;
BEGIN TRANSACTION;
DECLARE @map TABLE (team_id int PRIMARY KEY, from_name nvarchar(256), to_name nvarchar(256));
INSERT INTO @map VALUES
  (1, N'Mock Objects FC', N'Synthetic FC 1'),
  (2, N'Test Fixtures United', N'Synthetic FC 2'),
  (3, N'Stub City', N'Synthetic FC 3'),
  (4, N'Dummy Data Rovers', N'Synthetic FC 4'),
  (102, N'Tabs United', N'Metrica 1 · Equipo A'),
  (103, N'Spaces Athletic', N'Metrica 1 · Equipo B'),
  (104, N'Frontend FC', N'Metrica 2 · Equipo A'),
  (105, N'Backend Rovers', N'Metrica 2 · Equipo B'),
  (202, N'Merge Wanderers', N'SC 01 · Equipo A'),
  (203, N'Rebase City', N'SC 01 · Equipo B'),
  (204, N'Light Mode FC', N'SC 02 · Equipo A'),
  (205, N'Dark Mode United', N'SC 02 · Equipo B'),
  (206, N'Null Pointers', N'SC 03 · Equipo A'),
  (207, N'Undefined Athletic', N'SC 03 · Equipo B'),
  (208, N'Sync Rangers', N'SC 04 · Equipo A'),
  (209, N'Async Albion', N'SC 04 · Equipo B'),
  (210, N'Commit FC', N'SC 05 · Equipo A'),
  (211, N'Rollback Town', N'SC 05 · Equipo B'),
  (212, N'Segfault United', N'SC 06 · Equipo A'),
  (213, N'Kernel Panic FC', N'SC 06 · Equipo B'),
  (214, N'Infinite Loop City', N'SC 07 · Equipo A'),
  (215, N'Off-by-One Rovers', N'SC 07 · Equipo B'),
  (216, N'Race Condition FC', N'SC 08 · Equipo A'),
  (217, N'Deadlock Athletic', N'SC 08 · Equipo B');
IF EXISTS (SELECT 1 FROM @map m LEFT JOIN statsbomb.teams t WITH (UPDLOCK) ON t.team_id = m.team_id
           WHERE t.team_name IS NULL OR t.team_name NOT IN (m.from_name, m.to_name))
  THROW 50001, 'Nombre de equipo inesperado: no se cambia nada.', 1;
UPDATE t SET team_name = m.to_name
FROM statsbomb.teams t JOIN @map m ON m.team_id = t.team_id
WHERE t.team_name = m.from_name;
SELECT @@ROWCOUNT AS updated;
COMMIT;
