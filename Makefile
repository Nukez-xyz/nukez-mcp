SHELL      := /bin/bash
PYTHON     := .venv/bin/python
SERVER_DIR := ../nukez-mcp

# Package version (from pyproject.toml) and server version (single-sourced
# from the server repo's _version.py — this is what the registry listing tracks).
V  := $(shell python3 -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
SV := $(shell python3 -c "ns={};exec(open('$(SERVER_DIR)/nukez_mcp/_version.py').read(),ns);print(ns['__version__'])")

.PHONY: help test build push release registry deploy

help: ## Show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

test: ## Run the client test suite
	@$(PYTHON) -m pytest tests/ -q

build: ## Build wheel + sdist locally (sanity; CI builds the published artifacts)
	@rm -rf dist && uv build -q && ls dist/

push: ## Commit (if dirty) and push the GitHub repo
	@if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$$(git status --porcelain)" ]; then \
	  git add -A && git commit -m "nukez-mcp $(V)"; \
	else echo "working tree clean — nothing to commit"; fi
	@git push

release: ## Create GitHub release v$(V) → CI publishes to PyPI (trusted publishing)
	@if gh release view "v$(V)" >/dev/null 2>&1; then \
	  if git diff --quiet "v$(V)"..HEAD -- src pyproject.toml README.md; then \
	    echo "v$(V) already released and source unchanged — skipping"; \
	  else \
	    echo "ERROR: source changed since v$(V) was released."; \
	    echo "Bump [project].version in pyproject.toml, then re-run make deploy."; \
	    exit 1; \
	  fi; \
	else \
	  gh release create "v$(V)" --title "nukez-mcp $(V)" \
	    --notes "nukez-mcp $(V) — Python client for the hosted Nukez MCP (https://mcp.nukez.xyz/mcp)."; \
	  echo "waiting for the publish workflow..."; sleep 10; \
	  gh run watch $$(gh run list --workflow publish.yml --limit 1 --json databaseId -q '.[0].databaseId') --exit-status; \
	  echo "waiting for PyPI to serve $(V)..."; \
	  for i in $$(seq 1 24); do \
	    LIVE=$$(curl -s https://pypi.org/pypi/nukez-mcp/json | python3 -c "import json,sys;print(json.load(sys.stdin)['info']['version'])" 2>/dev/null); \
	    if [ "$$LIVE" = "$(V)" ]; then echo "PyPI now serves $(V)"; break; fi; \
	    sleep 5; \
	  done; \
	fi

registry: ## Sync server.json to server version $(SV) and publish to the MCP Registry if it moved
	@python3 -c "import json,pathlib; p=pathlib.Path('$(SERVER_DIR)/server.json'); d=json.loads(p.read_text()); \
changed = d['version'] != '$(SV)'; d['version']='$(SV)'; p.write_text(json.dumps(d, indent=2) + '\n'); \
print('server.json version -> $(SV)' + ('' if changed else ' (unchanged)'))"
	@LISTED=$$(curl -s "https://registry.modelcontextprotocol.io/v0/servers?search=nukez" | \
	  python3 -c "import json,sys; s=json.load(sys.stdin).get('servers',[]); print(s[0].get('server',s[0]).get('version','') if s else '')"); \
	if [ "$$LISTED" = "$(SV)" ]; then \
	  echo "registry already lists v$(SV) — skipping publish"; \
	else \
	  echo "registry lists '$$LISTED', publishing v$(SV)... (a browser device-flow login may open)"; \
	  cd $(SERVER_DIR) && (mcp-publisher publish || (mcp-publisher login github && mcp-publisher publish)); \
	fi

# One command: test → build → push repo → GitHub release (→ CI → PyPI) → registry sync.
# Idempotent: already-released versions and an up-to-date registry are skipped cleanly.
# To ship a new client version: bump [project].version in pyproject.toml first.
# To update the registry listing: bump the server repo's nukez_mcp/_version.py
# (its own `make deploy` ships the container), then run this.
deploy: test build push release registry ## Full pipeline: PyPI package + GitHub repo + MCP Registry
	@echo "── deploy complete: package v$(V) · registry v$(SV) ──"
