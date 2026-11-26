# Sourced by host launchers. Reads ONLY the database password and port from .env (never prints them);
# the rest of .env (session secret, password hash) stays out of the worker's environment.
env_value() { sed -n "s/^$1=//p" .env | tail -n 1 | sed -e "s/^'\(.*\)'\$/\1/" -e 's/^"\(.*\)"$/\1/'; }
pg_password=$(env_value POSTGRES_PASSWORD)
pg_port=$(env_value AIORG_PG_PORT)
export AIORG_DATABASE_URL="postgresql+psycopg://aiorg:${pg_password}@127.0.0.1:${pg_port:-5432}/aiorg"
unset pg_password pg_port
