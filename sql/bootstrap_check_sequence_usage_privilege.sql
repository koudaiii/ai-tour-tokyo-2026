SELECT has_sequence_privilege(
  current_user,
  quote_ident('public') || '.' || quote_ident(:'sequence_name'),
  'USAGE'
);
