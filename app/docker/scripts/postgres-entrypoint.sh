#!/bin/sh
set -eu

secret_file=/run/sakuramedia-config/postgres-password
config_file=/run/sakuramedia-config/config.toml
mkdir -p /run/sakuramedia-config
umask 077

if [ ! -s "$secret_file" ]; then
  if [ -s "${PGDATA:-/var/lib/postgresql/data}/PG_VERSION" ]; then
    echo "SakuraMedia 数据库密码文件缺失，但 PostgreSQL 数据目录不是空目录；为避免破坏数据，拒绝生成新密码。" >&2
    exit 1
  fi
  od -An -N32 -tx1 /dev/urandom | tr -d ' \n' > "$secret_file"
  chmod 600 "$secret_file"
fi
chmod 600 "$secret_file"

if [ ! -s "$config_file" ]; then
  db_password="$(cat "$secret_file")"
  {
    printf '%s\n' '[database]'
    printf '%s\n' 'engine = "postgres"'
    printf 'url = "postgresql://sakuramedia:%s@postgres:5432/sakuramedia"\n' "$db_password"
  } > "$config_file"
  chmod 600 "$config_file"
fi
chmod 600 "$config_file"

exec docker-entrypoint.sh postgres
