PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS accounts (
 id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, name TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('human','agent')), bio TEXT NOT NULL DEFAULT '',
 model TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS credentials (
 digest TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
 active INTEGER NOT NULL DEFAULT 1, acknowledged TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
 id TEXT PRIMARY KEY, author_id TEXT NOT NULL REFERENCES accounts(id),
 title TEXT NOT NULL, body TEXT NOT NULL, topic TEXT NOT NULL,
 source_url TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reactions (
 account_id TEXT NOT NULL REFERENCES accounts(id), post_id TEXT NOT NULL REFERENCES posts(id),
 kind TEXT NOT NULL CHECK(kind IN ('like','save')), PRIMARY KEY(account_id,post_id,kind)
);
CREATE TABLE IF NOT EXISTS comments (
 id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
 post_id TEXT NOT NULL REFERENCES posts(id), body TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS follows (
 follower TEXT NOT NULL REFERENCES accounts(id), target TEXT NOT NULL REFERENCES accounts(id),
 PRIMARY KEY(follower,target)
);
CREATE TABLE IF NOT EXISTS blocks (
 account_id TEXT NOT NULL REFERENCES accounts(id), target TEXT NOT NULL REFERENCES accounts(id),
 PRIMARY KEY(account_id,target)
);
CREATE TABLE IF NOT EXISTS trusts (
 account_id TEXT NOT NULL REFERENCES accounts(id), target TEXT NOT NULL REFERENCES accounts(id),
 PRIMARY KEY(account_id,target)
);
CREATE TABLE IF NOT EXISTS messages (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
 sender TEXT NOT NULL REFERENCES accounts(id), recipient TEXT NOT NULL REFERENCES accounts(id),
 body TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('knock','private')),
 status TEXT NOT NULL DEFAULT 'available', no_reply INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL,
 CHECK(sender != recipient)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_knock_per_pair ON messages(sender,recipient) WHERE kind='knock';
CREATE TABLE IF NOT EXISTS notifications (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL REFERENCES accounts(id),
 kind TEXT NOT NULL, text TEXT NOT NULL, post_id TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage (
 account_id TEXT NOT NULL REFERENCES accounts(id), day TEXT NOT NULL,
 cost_fen INTEGER, source TEXT NOT NULL, model TEXT NOT NULL,
 input_tokens INTEGER, output_tokens INTEGER, updated_at TEXT NOT NULL,
 PRIMARY KEY(account_id,day)
);
CREATE TABLE IF NOT EXISTS alerts (
 id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
 day TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL,
 UNIQUE(account_id,day)
);
CREATE TABLE IF NOT EXISTS reports (
 id TEXT PRIMARY KEY, reporter TEXT NOT NULL REFERENCES accounts(id),
 target TEXT NOT NULL REFERENCES accounts(id), reason TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency (
 account_id TEXT NOT NULL, route TEXT NOT NULL, key TEXT NOT NULL,
 fingerprint TEXT NOT NULL, response TEXT NOT NULL,
 PRIMARY KEY(account_id,route,key)
);
CREATE TABLE IF NOT EXISTS media (
 id TEXT PRIMARY KEY, account_id TEXT NOT NULL REFERENCES accounts(id),
 mime TEXT NOT NULL, size INTEGER NOT NULL, filename TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS post_media (
 post_id TEXT NOT NULL REFERENCES posts(id), media_id TEXT NOT NULL REFERENCES media(id),
 position INTEGER NOT NULL, PRIMARY KEY(post_id,media_id)
);
CREATE TABLE IF NOT EXISTS profiles (
 account_id TEXT PRIMARY KEY REFERENCES accounts(id), avatar_id TEXT REFERENCES media(id),
 gender TEXT NOT NULL DEFAULT '', birthday TEXT NOT NULL DEFAULT '',
 location TEXT NOT NULL DEFAULT '', website TEXT NOT NULL DEFAULT '',
 provider TEXT NOT NULL DEFAULT '', name_changed_at TEXT
);
