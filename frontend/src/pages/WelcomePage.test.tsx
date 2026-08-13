import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { WelcomePage } from './WelcomePage'

describe('WelcomePage', () => {
  it('describes the product and links to register and login', () => {
    render(
      <MemoryRouter>
        <WelcomePage />
      </MemoryRouter>,
    )

    expect(screen.getByText('NewCardForMe')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', {
        name: /Find your next favorite credit card/i,
      }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /Create an account/i }),
    ).toHaveAttribute('href', '/register')
    expect(screen.getByRole('link', { name: /Log in/i })).toHaveAttribute(
      'href',
      '/login',
    )
  })
})
