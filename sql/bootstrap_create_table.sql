DROP TABLE IF EXISTS comments;
DROP TABLE IF EXISTS posts;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  account_name varchar(64) NOT NULL UNIQUE,
  passhash varchar(128) NOT NULL,
  authority smallint NOT NULL DEFAULT 0,
  del_flg smallint NOT NULL DEFAULT 0,
  created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE posts (
  id SERIAL PRIMARY KEY,
  user_id int NOT NULL,
  mime varchar(64) NOT NULL,
  imgdata bytea NOT NULL,
  body text NOT NULL,
  created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE comments (
  id SERIAL PRIMARY KEY,
  post_id int NOT NULL,
  user_id int NOT NULL,
  comment text NOT NULL,
  created_at timestamp NOT NULL DEFAULT CURRENT_TIMESTAMP
);
