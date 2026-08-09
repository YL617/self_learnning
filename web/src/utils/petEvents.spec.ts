import { describe, expect, it } from 'vitest'

import { petEvents } from './petEvents'

describe('petEvents', () => {
  it('delivers events and unsubscribes cleanly', () => {
    const received: string[] = []
    const off = petEvents.on((event) => received.push(event.kind))

    petEvents.emit({ kind: 'focus' })
    petEvents.emit({ kind: 'plan' })
    off()
    petEvents.emit({ kind: 'wrong-book' })

    expect(received).toEqual(['focus', 'plan'])
  })
})
