export interface DraftPart {
  text: string
  /** True when `text` is a [PLACEHOLDER] the owner must fill in. */
  placeholder: boolean
}

/** Splits a draft body so [PLACEHOLDER] fields can be highlighted. */
export function splitPlaceholders(body: string): DraftPart[] {
  const parts: DraftPart[] = []
  const pattern = /\[[A-Z0-9_]+\]/g
  let last = 0
  for (const match of body.matchAll(pattern)) {
    const start = match.index ?? 0
    if (start > last) parts.push({ text: body.slice(last, start), placeholder: false })
    parts.push({ text: match[0], placeholder: true })
    last = start + match[0].length
  }
  if (last < body.length) parts.push({ text: body.slice(last), placeholder: false })
  return parts
}
