import { API_BASE } from '../config'
import { getSession } from '../state/session'
import { ApiError, parseErrorBody } from './errors'

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE'

/** The only place that calls fetch. Components use the functions in endpoints.ts. */
export async function request<T>(method: Method, path: string, body?: unknown): Promise<T> {
  const session = getSession()

  // Dev toggle: pretend the server broke, to show the API-error UI.
  if (session.force500) {
    throw new ApiError(500, 'INTERNAL_ERROR', 'Forced error (dev toggle)')
  }

  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: {
        'X-User-Id': session.userId,
        ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, undefined, 'Network error')
  }

  const text = await res.text()
  let json: unknown = undefined
  if (text) {
    try {
      json = JSON.parse(text)
    } catch {
      /* non-JSON body */
    }
  }

  if (!res.ok) throw parseErrorBody(res.status, json)
  return json as T
}
