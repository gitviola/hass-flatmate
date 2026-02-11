.PHONY: test sync-app-source

test:
	cd addon/hass_flatmate_service && . .venv/bin/activate && pytest

sync-app-source:
	./scripts/sync_app_service_src.sh
