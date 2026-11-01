/**
 * Typed Flutter <-> Three.js bridge.
 *
 * OUTBOUND (JS -> Flutter), fanned out over every available channel:
 *   1. flutter_inappwebview.callHandler('onAirspaceEvent', message)  — Android/iOS
 *   2. window.webkit.messageHandlers.airspace.postMessage(message)   — iOS WKWebView
 *   3. window.parent.postMessage(message, '*')                       — dev browser / hosts
 *
 * INBOUND (Flutter -> JS), two supported paths:
 *   A. webView.evaluateJavascript("window.airspaceBridge.dispatch({type:'…', …})")
 *   B. webView.postWebMessage / window.postMessage({type:'…', …}) — listened here.
 *      Flutter web posts commands as JSON STRINGS (Dart Maps do not survive
 *      the browser's structured clone), so string payloads are parsed here.
 */

const OUTBOUND_CHANNELS = [
    // webview_flutter JavaScriptChannel (Android/iOS) — receives a JSON string.
    message => {
        if (window.airspaceChannel && window.airspaceChannel.postMessage) {
            window.airspaceChannel.postMessage(JSON.stringify(message));
        }
    },
    message => {
        if (window.flutter_inappwebview && window.flutter_inappwebview.callHandler) {
            window.flutter_inappwebview.callHandler('onAirspaceEvent', message);
        }
    },
    message => {
        if (window.webkit && window.webkit.messageHandlers
            && window.webkit.messageHandlers.airspace) {
            window.webkit.messageHandlers.airspace.postMessage(message);
        }
    },
    message => {
        if (window.parent && window.parent !== window) window.parent.postMessage(message, '*');
        window.postMessage(message, '*');
    },
];

export function createBridge() {
    const commandHandlers = new Map();

    function emit(type, payload = {}) {
        // Keep the wire small: JSON-safe, flat, timestamped.
        const message = { type, ...payload, timestamp: Date.now() };
        for (const send of OUTBOUND_CHANNELS) {
            try {
                send(message);
            } catch (error) {
                // A missing channel is normal (e.g. no flutter_inappwebview in dev).
            }
        }
    }

    function onCommand(type, handler) {
        commandHandlers.set(type, handler);
    }

    function dispatch(message) {
        if (!message || typeof message !== 'object' || typeof message.type !== 'string') return;
        const handler = commandHandlers.get(message.type);
        if (!handler) return;
        try {
            Promise.resolve(handler(message)).catch(error => {
                emit('airspace:error', { message: String((error && error.message) || error) });
            });
        } catch (error) {
            emit('airspace:error', { message: String((error && error.message) || error) });
        }
    }

    window.addEventListener('message', event => {
        let data = event.data;
        // Flutter web posts commands as JSON strings — Dart Maps don't
        // survive the browser's structured clone, so posting the Map
        // directly arrived as an empty object and commands were dropped.
        if (typeof data === 'string') {
            try {
                data = JSON.parse(data);
            } catch (_) {
                return; // not our message
            }
        }
        dispatch(data);
    });

    // Direct-call surface for evaluateJavascript from Flutter.
    window.airspaceBridge = { dispatch };

    return { emit, onCommand, dispatch };
}