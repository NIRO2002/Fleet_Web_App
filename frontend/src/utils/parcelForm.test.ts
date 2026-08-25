import { describe, expect, it } from 'vitest'
import { emptyParcelDraft, parcelDraftToInput } from './format'

const valid = () => ({ ...emptyParcelDraft('P401'), depot_id: 'D-CMB-002', delivery_date: '2026-01-05', latitude: '6.86', longitude: '79.89', weight_kg: '12.5', volume_m3: '0.065', time_window_start: '09:00', time_window_end: '12:00', length_cm: '60', width_cm: '40', height_cm: '30', hazardous: true, hazmat_class: '3', requires_refrigeration: true, temp_min_celsius: '2', temp_max_celsius: '8' })

describe('full parcel form conversion', () => {
  it('sends ISO scope and every editable special-cargo field', () => {
    const result = parcelDraftToInput(valid())
    expect(result).toMatchObject({ parcel_id: 'P401', depot_id: 'D-CMB-002', delivery_date: '2026-01-05', hazardous: true, hazmat_class: '3', requires_refrigeration: true, temp_min_celsius: 2, temp_max_celsius: 8 })
    expect(result).not.toHaveProperty('status')
    expect(result).not.toHaveProperty('cluster_id')
  })
  it('requires an end time after the start time', () => {
    expect(() => parcelDraftToInput({ ...valid(), time_window_end: '08:00' })).toThrow(/after/)
  })
  it('requires all dimensions or none', () => {
    expect(() => parcelDraftToInput({ ...valid(), height_cm: '' })).toThrow(/all three/)
  })
})
