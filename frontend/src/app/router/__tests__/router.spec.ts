import { describe, expect, it } from 'vitest'
import { router } from '../index'

describe('router legacy static HTML redirects', () => {
  it.each([
    ['/archive.html', '/archive'],
    ['/reports.html', '/reports'],
    ['/sources.html', '/sources'],
    ['/status.html', '/status'],
  ])('redirects %s to %s', (path, target) => {
    const route = router.getRoutes().find((record) => record.path === path) as
      | { redirect?: unknown }
      | undefined

    expect(route?.redirect).toBe(target)
  })
})
