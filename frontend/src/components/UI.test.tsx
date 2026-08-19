import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { LoadingState, PrimaryButton } from './UI'

describe('loading feedback', () => {
  it('shows an accessible please-wait status for slow page loads', () => {
    render(<LoadingState message="Please wait while parcels are loading…" />)

    expect(screen.getByRole('status')).toHaveTextContent('Please wait while parcels are loading…')
  })

  it('disables a busy action and replaces its label with please wait', () => {
    render(<PrimaryButton loading>Run optimization</PrimaryButton>)

    expect(screen.getByRole('button', { name: 'Please wait…' })).toBeDisabled()
    expect(screen.queryByText('Run optimization')).not.toBeInTheDocument()
  })
})
