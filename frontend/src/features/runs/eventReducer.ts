import type { DomainEvent, EventState } from "../../types/events";
export function eventReducer(state: EventState, event: DomainEvent): EventState {
  if (event.sequence <= state.cursor && state.events.some((item) => item.sequence === event.sequence)) return state;
  return { cursor: Math.max(state.cursor, event.sequence), gap: event.sequence > state.cursor + 1 ? { expected: state.cursor + 1, received: event.sequence } : state.gap, events: [...state.events, event].sort((a, b) => a.sequence - b.sequence) };
}
