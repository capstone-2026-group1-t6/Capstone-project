/**
 * Placeholder entrypoint.
 *
 * This scaffold only wires up the build/Docker/CI plumbing (Vite, nginx,
 * docker-compose, GitHub Actions). The actual UI and styling is Eshraq's —
 * nothing here is meant to be kept. Replace this component freely.
 *
 * The API runs at the URL in VITE_API_BASE_URL (see .env.example) with a
 * POST /query endpoint (see the backend's app/routers/query.py for the
 * request/response shape) and a GET /health endpoint.
 */
export default function App() {
  return (
    <div style={{ padding: "2rem", fontFamily: "sans-serif" }}>
      <h1>rag-platform frontend</h1>
      <p>Placeholder — build the real UI here.</p>
    </div>
  );
}
