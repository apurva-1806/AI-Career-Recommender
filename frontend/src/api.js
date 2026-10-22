// Thin client for the FastAPI backend.
const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

function describeError(body, status) {
  const detail = body?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    return detail.map((item) => String(item.msg || '').replace(/^Value error, /, '')).join(' ')
  }
  return `The server returned an error (${status}).`
}

async function request(path, options = {}) {
  let response
  try {
    // credentials: 'include' sends the session cookie, also when the API is on another origin
    response = await fetch(`${BASE}${path}`, { credentials: 'include', ...options })
  } catch {
    throw new Error('Cannot reach the API. Start the backend on port 8000, then try again.')
  }
  let body = null
  try {
    body = await response.json()
  } catch {
    // Non-JSON body (for example a proxy error page); handled below.
  }
  if (response.status === 204) return null
  if (!response.ok) {
    if (response.status >= 500 && !body) {
      throw new Error('Cannot reach the API. Start the backend on port 8000, then try again.')
    }
    const error = new Error(describeError(body, response.status))
    error.status = response.status
    throw error
  }
  return body
}

export const getMeta = () => request('/api/meta')

export const getCareers = () => request('/api/careers')

export const getRecommendations = (profile, topK) =>
  request(`/api/recommend${topK ? `?top_k=${topK}` : ''}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(profile),
  })

export const parseResume = (file) => {
  const form = new FormData()
  form.append('file', file)
  return request('/api/resume/parse', { method: 'POST', body: form })
}
