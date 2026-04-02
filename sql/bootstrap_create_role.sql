SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L',
  'isuconp',
  'isuconp'
)
WHERE NOT EXISTS (
  SELECT 1
  FROM pg_roles
  WHERE rolname = 'isuconp'
)
\gexec
