# Capstone-project

## Run the project with Docker

From the repository root, start the full stack with:

```bash
docker compose up --build
```

This will start:
- API: http://localhost:8000
- Frontend: http://localhost:5173
- Prometheus: http://localhost:9090

To stop the containers:

```bash
docker compose down
```

The Docker setup uses the project root as the Compose entrypoint, so running the command from the repository root starts everything together.
