import { describe, expect, it } from 'vitest'
import { DEMO_DEPOT_ID, demoDeliveryDate } from './parcelService'

describe('bundled dataset planning instance', () => {
  it('targets an instance present in parcels_sample_36000.csv', () => {
    expect(DEMO_DEPOT_ID).toBe('D-CMB-001')
    expect(demoDeliveryDate()).toBe('2026-01-05')
  })
})
