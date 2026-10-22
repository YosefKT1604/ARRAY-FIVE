const KEY = 'scdc.dev'

/**
 * The dev panel is hidden unless the URL has ?dev=1 (so judges never see it).
 * The flag is remembered for the tab, because in-app navigation drops the query string.
 */
export function isDevMode(): boolean {
  try {
    if (new URLSearchParams(window.location.search).get('dev') === '1') sessionStorage.setItem(KEY, '1')
    return sessionStorage.getItem(KEY) === '1'
  } catch {
    return new URLSearchParams(window.location.search).get('dev') === '1'
  }
}
