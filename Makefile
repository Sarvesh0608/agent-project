.PHONY: install render-stg render-prod deploy-stg deploy-prod dry-run-stg dry-run-prod clean

ENV ?= stg

install:
	pip install -r requirements.txt

# ── Render ────────────────────────────────────────────────────────────────────
render-stg:
	ENV=stg python scripts/render.py

render-prod:
	ENV=prod python scripts/render.py

render:
	ENV=$(ENV) python scripts/render.py

# ── Deploy ────────────────────────────────────────────────────────────────────
deploy-stg: render-stg
	ENV=stg python scripts/deploy.py

deploy-prod: render-prod
	ENV=prod python scripts/deploy.py

dry-run-stg: render-stg
	ENV=stg python scripts/deploy.py --dry-run

dry-run-prod: render-prod
	ENV=prod python scripts/deploy.py --dry-run

# ── Utility ───────────────────────────────────────────────────────────────────
clean:
	rm -rf rendered/
