const REASONS: Record<string, string> = {
  effect_unknown:
    'The worker stopped while a model call was in progress, so it may or may not have gone through. Retrying can use quota twice.',
  call_maybe_sent:
    'The model call failed after it may have reached the provider (for example a timeout). Retrying can use quota twice.',
  crash_loop: 'The worker crashed several times while running this task.',
  AllRoutesFailed: 'Every model provider for this task failed.',
  DataClassRefused: 'No allowed model may receive this data.',
  PromptTooLarge: 'The task text is too long for the model.',
}

export const reasonText = (reason: string | null | undefined) =>
  reason ? (REASONS[reason] ?? reason) : 'No reason was recorded.'
