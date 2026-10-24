import type { UnresolvedField } from '../types/contracts'

const ID = /^[A-Z]{1,3}-\d{2,4}$/

/** "a", "a or b", "a, b or c" */
const joinOr = (items: string[]) => (items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} or ${items[items.length - 1]}`)

/** "7 and 15", "1, 2 and 3" */
const joinAnd = (items: string[]) => (items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`)

/**
 * A question from the extraction in plain words: suggestions by name ("Folding Chairs or Round Tables"), and several
 * quantities asked once instead of repeated. `humanize` is the same lookup the rest of the UI uses.
 */
export function plainQuestion(question: string, humanize: (text: string) => string): string {
  const quantities = /the message gives different quantities: ([\d, ]+)\./i.exec(question)
  if (quantities) {
    const numbers = quantities[1].split(',').map((n) => n.trim()).filter(Boolean)
    return `The message gives ${numbers.length === 2 ? 'two' : 'several'} numbers (${joinAnd(numbers)}). Which one is for this item?`
  }
  return question.replace(/Suggestions: ([^.]*)\./, (_all, list: string) => {
    const names = list.split(',').map((s) => s.trim()).filter(Boolean).map((s) => (ID.test(s) || /^\d{4}-\d{2}-\d{2}$/.test(s) ? humanize(s) : s))
    return `Suggestions: ${joinOr(names)}.`
  })
}

/** True when the item could not be told apart because the message mentions several. */
export const mentionsSeveralItems = (unresolved: UnresolvedField[]) =>
  unresolved.some((u) => u.field === 'resource_id' && (u.candidates?.length ?? 0) > 1)

export const SEVERAL_ITEMS_TIP =
  'This message mentions more than one item. One report covers one item: choose the item and its number below, then report the other item separately.'
