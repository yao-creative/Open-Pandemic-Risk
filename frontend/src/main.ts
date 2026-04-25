type ReadyzResponse = {
  ready: boolean
  checks?: Record<string, string>
  details?: string[]
}

const statusEl = document.getElementById('status')
const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

if (!statusEl) {
  throw new Error('Missing status element')
}

async function checkReady(): Promise<void> {
  try {
    const res = await fetch(`${apiBase}/readyz`)
    const data = (await res.json()) as ReadyzResponse

    statusEl.textContent = JSON.stringify(
      {
        http_status: res.status,
        backend_ready: Boolean(data.ready),
        checks: data.checks,
        details: data.details
      },
      null,
      2
    )
  } catch (err) {
    statusEl.textContent = `request_failed: ${String(err)}`
  }
}

void checkReady()
