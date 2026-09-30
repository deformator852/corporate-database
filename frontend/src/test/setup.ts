import "@testing-library/jest-dom/vitest";
import {cleanup} from "@testing-library/react";
import {afterEach, beforeEach} from "vitest";

import {useSessionStore} from "@/shared/auth/session-store";
import {FakeWebSocket} from "./socket";

class FakeIntersectionObserver {
    static instances: FakeIntersectionObserver[] = [];
    readonly targets = new Set<Element>();
    readonly callback: IntersectionObserverCallback;

    constructor(callback: IntersectionObserverCallback) {
        this.callback = callback;
        FakeIntersectionObserver.instances.push(this);
    }

    observe(target: Element) {
        this.targets.add(target);
    }

    unobserve(target: Element) {
        this.targets.delete(target);
    }

    disconnect() {
        this.targets.clear();
    }

    takeRecords() {
        return [];
    }
}

/** Scrolls every watched "load more" sentinel into view. */
export function scrollToEnd(): void {
    for (const observer of FakeIntersectionObserver.instances) {
        const entries = [...observer.targets].map(
            (target) => ({isIntersecting: true, target}) as IntersectionObserverEntry,
        );
        if (entries.length > 0) {
            observer.callback(entries, observer as unknown as IntersectionObserver);
        }
    }
}

Object.assign(globalThis, {
    WebSocket: FakeWebSocket,
    IntersectionObserver: FakeIntersectionObserver,
    ResizeObserver: class {
        observe() {}
        unobserve() {}
        disconnect() {}
    },
});
window.matchMedia ??= ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
})) as typeof window.matchMedia;
Element.prototype.scrollIntoView ??= () => {};

beforeEach(() => {
    useSessionStore.setState({user: null, status: "idle", error: null});
    FakeWebSocket.instances = [];
    FakeIntersectionObserver.instances = [];
    document.cookie.split("; ").forEach((cookie) => {
        document.cookie = `${cookie.split("=")[0]}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
    });
});

afterEach(() => {
    cleanup();
});
