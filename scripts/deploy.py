#!/usr/bin/env python3
"""
Deploy rendered SQL files to Snowflake in order.

Usage:
    ENV=stg python scripts/deploy.py
    ENV=prod python scripts/deploy.py --dry-run

Required env vars:
    SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD (or SNOWFLAKE_PRIVATE_KEY_PATH),
    SNOWFLAKE_ROLE, SNOWFLAKE_WAREHOUSE
"""

import argparse
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def get_connection_params(env_name: str) -> dict:
    with open(ROOT / "config" / "environments.yml") as f:
        env_cfg = yaml.safe_load(f)["environments"][env_name]

    required = ["SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER"]
    missing = [v for v in required if not os.environ.get(v)]
    if missing:
        print(f"ERROR: missing environment variables: {missing}", file=sys.stderr)
        sys.exit(1)

    params = {
        "account":   os.environ["SNOWFLAKE_ACCOUNT"],
        "user":      os.environ["SNOWFLAKE_USER"],
        "role":      os.environ.get("SNOWFLAKE_ROLE", env_cfg["snowflake"]["role"]),
        "warehouse": env_cfg["warehouse"]["name"],
    }

    private_key_path = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH")
    if private_key_path:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives import serialization

        with open(private_key_path, "rb") as key_file:
            p_key = serialization.load_pem_private_key(
                key_file.read(),
                password=os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE", "").encode() or None,
                backend=default_backend(),
            )
        params["private_key"] = p_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    else:
        password = os.environ.get("SNOWFLAKE_PASSWORD")
        if not password:
            print("ERROR: set SNOWFLAKE_PASSWORD or SNOWFLAKE_PRIVATE_KEY_PATH", file=sys.stderr)
            sys.exit(1)
        params["password"] = password

    return params


def execute_file(cursor, sql_file: Path, dry_run: bool) -> int:
    sql = sql_file.read_text()
    statements = [s.strip() for s in sql.split(";") if s.strip() and not s.strip().startswith("--")]
    executed = 0
    for stmt in statements:
        if dry_run:
            print(f"    [DRY RUN] {stmt[:80].replace(chr(10), ' ')}...")
        else:
            cursor.execute(stmt)
        executed += 1
    return executed


def deploy(env_name: str, dry_run: bool):
    rendered_dir = ROOT / "rendered" / env_name
    if not rendered_dir.exists():
        print(f"ERROR: rendered directory not found: {rendered_dir}", file=sys.stderr)
        print("Run: python scripts/render.py --env", env_name, file=sys.stderr)
        sys.exit(1)

    sql_files = sorted(rendered_dir.glob("*.sql"))
    if not sql_files:
        print(f"ERROR: no SQL files in {rendered_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Deploying {len(sql_files)} SQL files to Snowflake ({env_name})"
          + (" [DRY RUN]" if dry_run else ""))

    if dry_run:
        for f in sql_files:
            print(f"\n>>> {f.name}")
            execute_file(None, f, dry_run=True)
        print("\nDry run complete.")
        return

    import snowflake.connector

    params = get_connection_params(env_name)
    conn = snowflake.connector.connect(**params)
    cursor = conn.cursor()

    total_stmts = 0
    try:
        for sql_file in sql_files:
            print(f"\n>>> Executing {sql_file.name}")
            n = execute_file(cursor, sql_file, dry_run=False)
            total_stmts += n
            print(f"    {n} statements OK")
        conn.commit()
    except Exception as exc:
        conn.rollback()
        print(f"\nERROR during deployment: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        cursor.close()
        conn.close()

    print(f"\nDeployment complete — {total_stmts} statements executed.")


def main():
    parser = argparse.ArgumentParser(description="Deploy rendered SQL to Snowflake")
    parser.add_argument("--env", default=os.environ.get("ENV", ""))
    parser.add_argument("--dry-run", action="store_true", help="Print SQL without executing")
    args = parser.parse_args()

    if not args.env:
        print("ERROR: set --env or export ENV=stg|prod", file=sys.stderr)
        sys.exit(1)

    deploy(args.env.lower().lstrip("_"), args.dry_run)


if __name__ == "__main__":
    main()
