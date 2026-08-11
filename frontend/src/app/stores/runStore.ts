import { useSyncExternalStore } from "react";
import type { DomainEvent, EventState } from "../../types/events";

let state: EventState = { cursor: 0, gap: null, events: [] };
const listeners = new Set<() => void>();

export function reduceEvents(incoming: DomainEvent[]) {
  const known = new Set(state.events.map((event) => event.sequence));
  let gap = state.gap;
  const ordered = [...incoming].sort((a, b) => a.sequence - b.sequence);
  for (const event of ordered) {
    if (known.has(event.sequence)) continue;
    if (event.sequence > state.cursor + 1) gap = { expected: state.cursor + 1, received: event.sequence };
    state = { ...state, cursor: Math.max(state.cursor, event.sequence), events: [...state.events, event], gap };
    known.add(event.sequence);
  }
  listeners.forEach((listener) => listener());
}

export function useRunStore() { return useSyncExternalStore((listener) => { listeners.add(listener); return () => listeners.delete(listener); }, () => state); }
