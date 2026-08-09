export type PetEventKind = 'focus' | 'plan' | 'wrong-book'

export interface PetEvent {
  kind: PetEventKind
}

type Listener = (event: PetEvent) => void

const listeners = new Set<Listener>()

export const petEvents = {
  emit(event: PetEvent) {
    listeners.forEach((listener) => listener(event))
  },
  on(listener: Listener) {
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  },
}
