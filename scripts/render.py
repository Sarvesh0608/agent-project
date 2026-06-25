#!/usr/bin/env python3
"""
Render Jinja2 SQL templates for a target environment.

Usage:
    ENV=stg python scripts/render.py
    ENV=prod python scripts/render.py --output-dir rendered/prod
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined


ROOT = Path(__file__).resolve().parent.parent


def load_config(env_name: str) -> dict:
    with open(ROOT / "config" / "environments.yml") as f:
        envs = yaml.safe_load(f)["environments"]
    with open(ROOT / "config" / "settings.yml") as f:
        settings = yaml.safe_load(f)

    if env_name not in envs:
        print(f"ERROR: unknown environment '{env_name}'. Valid: {list(envs)}", file=sys.stderr)
        sys.exit(1)

    return {"env": envs[env_name], "settings": settings}


def build_jinja_env() -> Environment:
    jinja_env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    jinja_env.globals["now"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    return jinja_env


def render_templates(env_name: str, output_dir: Path) -> list[Path]:
    context = load_config(env_name)
    jinja_env = build_jinja_env()

    # Ordered list of templates to render (deploy order matters)
    templates = [
        ("ddl/databases.sql.j2",      "01_databases.sql"),
        ("ddl/warehouses.sql.j2",     "02_warehouses.sql"),
        ("ddl/schemas.sql.j2",        "03_schemas.sql"),
        ("ddl/roles.sql.j2",          "04_roles.sql"),
        ("bronze/stages.sql.j2",      "05_bronze_stages.sql"),
        ("bronze/raw_tables.sql.j2",  "06_bronze_tables.sql"),
        ("silver/transformed.sql.j2", "07_silver_tables.sql"),
        ("gold/aggregated.sql.j2",    "08_gold_objects.sql"),
    ]

    output_dir.mkdir(parents=True, exist_ok=True)
    rendered_files = []

    for template_path, output_name in templates:
        tmpl = jinja_env.get_template(template_path)
        sql = tmpl.render(**context)

        out_file = output_dir / output_name
        out_file.write_text(sql)
        print(f"  rendered: {template_path} -> {out_file.relative_to(ROOT)}")
        rendered_files.append(out_file)

    return rendered_files


def main():
    parser = argparse.ArgumentParser(description="Render Snowflake SQL templates")
    parser.add_argument(
        "--env",
        default=os.environ.get("ENV", ""),
        help="Target environment (stg|prod). Falls back to $ENV variable.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory (default: rendered/<env>)",
    )
    args = parser.parse_args()

    if not args.env:
        print("ERROR: set --env or export ENV=stg|prod", file=sys.stderr)
        sys.exit(1)

    env_name = args.env.lower().lstrip("_")
    output_dir = args.output_dir or (ROOT / "rendered" / env_name)

    print(f"Rendering templates for environment: {env_name}")
    files = render_templates(env_name, output_dir)
    print(f"\nDone — {len(files)} files written to {output_dir.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
