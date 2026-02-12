.PHONY: test sync-app-source dev dev-down dev-logs dev-clean

test:
	cd addon/hass_flatmate_service && . .venv/bin/activate && pytest

sync-app-source:
	./scripts/sync_app_service_src.sh

dev:
	@mkdir -p dev/backend-data
	docker compose up -d --build
	@echo ""
	@echo "=== Hass Flatmate Dev Environment ==="
	@echo ""
	@echo "  HA:      http://localhost:8123"
	@echo "  Backend: http://localhost:8099"
	@echo ""
	@echo "  First-time setup:"
	@echo "    1. Open http://localhost:8123 and create a user"
	@echo "    2. Settings → Integrations → Add → 'Hass Flatmate'"
	@echo "    3. Base URL: http://backend:8099"
	@echo "    4. API Token: dev-token"
	@echo ""
	@echo "  Hot-reload:"
	@echo "    Backend Python  → auto (uvicorn --reload)"
	@echo "    Integration .py → HA UI: Integration → Reload"
	@echo "    Frontend JS     → hard-refresh browser"
	@echo ""

dev-down:
	docker compose down

dev-logs:
	docker compose logs -f

dev-clean:
	docker compose down -v
	rm -rf dev/backend-data dev/ha-config/.storage dev/ha-config/*.db dev/ha-config/.HA_VERSION
