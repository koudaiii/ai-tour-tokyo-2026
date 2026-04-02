SELECT has_table_privilege(
  current_user,
  quote_ident('public') || '.' || quote_ident(:'table_name'),
  :'privilege_name'
);
