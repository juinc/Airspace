const BRIDGE_VERSION = 1;
const COMMANDS = new Set(['loadScenario', 'setCamera', 'toggleLayer', 'setApiBase']);

function decodeMessage(value) {
    if (typeof value === 'string') {
        try {
            return JSON.parse(value);
        } catch {
            return null;
        }
    }
    return value && typeof value === 'object' ? value : null;
}

export function createAirspaceBridge(onCommand) {
    function receive(value) {
        const message = decodeMessage(value);
        if (!message || message.version !== BRIDGE_VERSION || message.type !== 'command') return;
        if (!COMMANDS.has(message.action)) return;
        onCommand(message);
    }

    window.AirspaceThree = Object.freeze({ receiveMessage: receive });

    window.addEventListener('message', event => {
        if (window.parent === window || event.source !== window.parent) return;
        receive(event.data);
    });

    if (window.chrome && window.chrome.webview) {
        window.chrome.webview.addEventListener('message', event => receive(event.data));
    }

    return {
        isEmbedded() {
            return window.parent !== window
                || Boolean(window.AirspaceBridge && window.AirspaceBridge.postMessage)
                || Boolean(window.chrome && window.chrome.webview);
        },

        emit(event, data = {}) {
            const message = { version: BRIDGE_VERSION, type: 'event', event, ...data };
            const serialized = JSON.stringify(message);

            if (window.AirspaceBridge && window.AirspaceBridge.postMessage) {
                window.AirspaceBridge.postMessage(serialized);
            } else if (window.chrome && window.chrome.webview) {
                window.chrome.webview.postMessage(serialized);
            } else if (window.parent !== window) {
                window.parent.postMessage(message, '*');
            } else {
                window.dispatchEvent(new CustomEvent('airspace:bridge', { detail: message }));
            }
        },
    };
}
