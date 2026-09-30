/** Stand-in for the browser WebSocket; tests play the server side. */
export class FakeWebSocket extends EventTarget {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;
    static instances: FakeWebSocket[] = [];

    readonly CONNECTING = 0;
    readonly OPEN = 1;
    readonly CLOSING = 2;
    readonly CLOSED = 3;
    readyState = FakeWebSocket.CONNECTING;
    readonly sent: unknown[] = [];
    readonly url: string;

    constructor(url: string) {
        super();
        this.url = url;
        FakeWebSocket.instances.push(this);
        queueMicrotask(() => {
            if (this.readyState === FakeWebSocket.CONNECTING) {
                this.readyState = FakeWebSocket.OPEN;
                this.dispatchEvent(new Event("open"));
            }
        });
    }

    send(data: string): void {
        this.sent.push(JSON.parse(data));
    }

    close(code = 1000): void {
        if (this.readyState === FakeWebSocket.CLOSED) {
            return;
        }
        this.readyState = FakeWebSocket.CLOSED;
        this.dispatchEvent(Object.assign(new Event("close"), {code}));
    }

    /** The server sends `data` (JSON-encoded). */
    receive(data: unknown): void {
        this.dispatchEvent(new MessageEvent("message", {data: JSON.stringify(data)}));
    }

    /** The newest open socket whose URL ends with `path`. */
    static at(path: string): FakeWebSocket {
        const socket = [...FakeWebSocket.instances]
            .reverse()
            .find((s) => s.url.endsWith(path) && s.readyState !== FakeWebSocket.CLOSED);
        if (!socket) {
            throw new Error(`No open socket for ${path}`);
        }
        return socket;
    }
}
