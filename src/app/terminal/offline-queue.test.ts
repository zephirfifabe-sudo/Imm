import { beforeEach, describe, expect, it, vi } from "vitest";
import { readQueue, enqueue, removeFromQueue, type QueuedClockEvent } from "./offline-queue";

function createMemoryStorage(): Storage {
  const store = new Map<string, string>();
  return {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
    clear: () => store.clear(),
    key: () => null,
    get length() {
      return store.size;
    },
  } as Storage;
}

function makeEvent(overrides: Partial<QueuedClockEvent> = {}): QueuedClockEvent {
  return {
    eventId: "11111111-1111-1111-1111-111111111111",
    employeeId: "emp-1",
    type: "CLOCK_IN",
    method: "PIN",
    occurredAt: "2026-09-07T09:02:00.000Z",
    ...overrides,
  };
}

describe("offline queue", () => {
  beforeEach(() => {
    vi.stubGlobal("window", { localStorage: createMemoryStorage() });
  });

  it("starts empty", () => {
    expect(readQueue()).toEqual([]);
  });

  it("stores an enqueued event", () => {
    const event = makeEvent();
    enqueue(event);
    expect(readQueue()).toEqual([event]);
  });

  it("preserves order across multiple events", () => {
    const first = makeEvent({ eventId: "a" });
    const second = makeEvent({ eventId: "b" });
    enqueue(first);
    enqueue(second);
    expect(readQueue().map((e) => e.eventId)).toEqual(["a", "b"]);
  });

  it("removes only the targeted event", () => {
    enqueue(makeEvent({ eventId: "a" }));
    enqueue(makeEvent({ eventId: "b" }));
    removeFromQueue("a");
    expect(readQueue().map((e) => e.eventId)).toEqual(["b"]);
  });

  it("recovers from corrupted storage instead of throwing", () => {
    (window.localStorage as Storage).setItem("klock_terminal_offline_queue", "not json");
    expect(readQueue()).toEqual([]);
  });
});
