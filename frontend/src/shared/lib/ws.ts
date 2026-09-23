export function connectSocket(
    url: string,
    onMessage: (data: string) => void,
): () => void {
    let closed = false;
    let socket: WebSocket | null = null;
    let timer: number | undefined;

    const open = () => {
        if (closed) {
            return;
        }
        const next = new WebSocket(url);
        socket = next;
        next.addEventListener("message", (event) => {
            if (typeof event.data === "string") {
                onMessage(event.data);
            }
        });
        next.addEventListener("close", () => {
            if (closed || socket !== next) {
                return;
            }
            timer = window.setTimeout(open, 2000);
        });
        next.addEventListener("error", () => {
            next.close();
        });
    };

    timer = window.setTimeout(open, 0);

    return () => {
        closed = true;
        if (timer !== undefined) {
            window.clearTimeout(timer);
        }
        socket?.close();
        socket = null;
    };
}
