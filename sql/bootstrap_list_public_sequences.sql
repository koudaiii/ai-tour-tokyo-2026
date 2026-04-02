SELECT COALESCE(string_agg(sequence_name, E'\n'), '')
FROM information_schema.sequences
WHERE sequence_schema = 'public';
