/**
 * Typed Flutter <-> Three.js bridge.
 *
 * OUTBOUND (JS -> Flutter), fanned out over every available channel:
 *   1. flutter_inappwebview.callHandler('onAirspaceEvent', message)  — Android/iOS
 *   2. window.webkit.messageHandlers.airspace.postMessage(message)   — iOS WKWebView
 *   3. window.parent.postMessage(JSON string, '*')                   — Flutter web / hosts
 *
 *   The postMessage channel carries JSON STRINGS, not objects: on Flutter
 *   web (dart2js) a plain JS object arriving via postMessage is NOT a
 *   Dart Map, so `data is Map` silently failed and every scene event was
 *   dropped. Strings survive the structured clone and the Dart host
 *   jsonDecodes them.
 *
 * INBOUND (Flutter -> JS), two supported paths:
 *   A. webView.evaluateJavascript("window.airspaceBridge.dispatch({type:'…', …})")
 *   B. postMessage — Flutter web posts commands as JSON strings (Dart Maps
 *      don't survive the structured clone), parsed here.
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
        if (window.chrome && window.chrome.webview) {
            window.chrome.webview.postMessage(message);
        }
    },
    message => {
        // Flutter web host — MUST be a string (see header comment).
        const json = JSON.stringify(message);
        if (window.parent && window.parent !== window) window.parent.postMessage(json, '*');
        window.postMessage(json, '*');
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
        // Both Flutter web directions use JSON strings — parse them here.
        if (typeof data === 'string') {
            try {
                data = JSON.parse(data);
            } catch (_) {
                return; // not our message
            }
        }
        dispatch(data);
    });

    if (window.chrome && window.chrome.webview) {
        window.chrome.webview.addEventListener('message', event => dispatch(event.data));
    }

    // Direct-call surface for evaluateJavascript from Flutter.
    window.airspaceBridge = { dispatch };

    return { emit, onCommand, dispatch };
}