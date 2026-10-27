-- Generado desde team-names.json. Equivalente a: node rename-teams.mjs
-- Una transacción; aborta si algún equipo no tiene el nombre esperado ni el final.
SET XACT_ABORT ON;
BEGIN TRANSACTION;
DECLARE @map TABLE (team_id int PRIMARY KEY, from_name nvarchar(256), to_name nvarchar(256));
INSERT INTO @map VALUES
  (1, N'Synthetic FC 1', N'Mock Objects FC'),
  (2, N'Synthetic FC 2', N'Test Fixtures United'),
  (3, N'Synthetic FC 3', N'Stub City'),
  (4, N'Synthetic FC 4', N'Dummy Data Rovers'),
  (102, N'Metrica 1 · Equipo A', N'Tabs United'),
  (103, N'Metrica 1 · Equipo B', N'Spaces Athletic'),
  (104, N'Metrica 2 · Equipo A', N'Frontend FC'),
  (105, N'Metrica 2 · Equipo B', N'Backend Rovers'),
  (202, N'SC 01 · Equipo A', N'Merge Wanderers'),
  (203, N'SC 01 · Equipo B', N'Rebase City'),
  (204, N'SC 02 · Equipo A', N'Light Mode FC'),
  (205, N'SC 02 · Equipo B', N'Dark Mode United'),
  (206, N'SC 03 · Equipo A', N'Null Pointers'),
  (207, N'SC 03 · Equipo B', N'Undefined Athletic'),
  (208, N'SC 04 · Equipo A', N'Sync Rangers'),
  (209, N'SC 04 · Equipo B', N'Async Albion'),
  (210, N'SC 05 · Equipo A', N'Commit FC'),
  (211, N'SC 05 · Equipo B', N'Rollback Town'),
  (212, N'SC 06 · Equipo A', N'Segfault United'),
  (213, N'SC 06 · Equipo B', N'Kernel Panic FC'),
  (214, N'SC 07 · Equipo A', N'Infinite Loop City'),
  (215, N'SC 07 · Equipo B', N'Off-by-One Rovers'),
  (216, N'SC 08 · Equipo A', N'Race Condition FC'),
  (217, N'SC 08 · Equipo B', N'Deadlock Athletic');
IF EXISTS (SELECT 1 FROM @map m LEFT JOIN statsbomb.teams t WITH (UPDLOCK) ON t.team_id = m.team_id
           WHERE t.team_name IS NULL OR t.team_name NOT IN (m.from_name, m.to_name))
  THROW 50001, 'Nombre de equipo inesperado: no se cambia nada.', 1;
UPDATE t SET team_name = m.to_name
FROM statsbomb.teams t JOIN @map m ON m.team_id = t.team_id
WHERE t.team_name = m.from_name;
SELECT @@ROWCOUNT AS updated;
COMMIT;
