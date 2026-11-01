/// Platform-adaptive scene host.
///  - Web (Chrome/Edge): IFrameElement + window.postMessage bridge.
///  - IO (Android/iOS): webview_flutter + JavaScriptChannel bridge.
export 'webview_host_stub.dart'
    if (dart.library.html) 'webview_host_web.dart'
    if (dart.library.io) 'webview_host_io.dart';