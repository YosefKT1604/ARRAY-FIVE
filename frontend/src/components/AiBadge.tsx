/** Rule 8: anything generated_by "model:..." is labelled AI-generated. */
export function AiBadge({ generatedBy }: { generatedBy: string | null | undefined }) {
  if (!generatedBy?.startsWith('model:')) return null
  return (
    <span className="inline-flex items-center rounded-full bg-info-bg px-2 py-0.5 text-xs font-semibold text-brand">
      AI-generated
    </span>
  )
}
