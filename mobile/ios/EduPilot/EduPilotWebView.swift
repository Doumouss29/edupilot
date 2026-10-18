import SwiftUI
import WebKit

struct EduPilotWebView: UIViewRepresentable {
    @Binding var isOnline: Bool

    func makeCoordinator() -> Coordinator { Coordinator(isOnline: $isOnline) }

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        configuration.websiteDataStore = .default()
        let view = WKWebView(frame: .zero, configuration: configuration)
        view.navigationDelegate = context.coordinator
        view.allowsBackForwardNavigationGestures = true
        view.scrollView.contentInsetAdjustmentBehavior = .automatic
        if let url = URL(string: "https://edupilot.ci/login") {
            view.load(URLRequest(url: url, cachePolicy: .useProtocolCachePolicy))
        }
        return view
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate {
        @Binding var isOnline: Bool
        init(isOnline: Binding<Bool>) {
            _isOnline = isOnline
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            isOnline = true
        }

        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!,
                     withError error: Error) {
            isOnline = false
        }

        func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = navigationAction.request.url else {
                decisionHandler(.cancel)
                return
            }
            let allowedHosts = ["edupilot.ci", "www.edupilot.ci"]
            if url.scheme == "https", let host = url.host?.lowercased(),
               allowedHosts.contains(host) {
                decisionHandler(.allow)
            } else {
                decisionHandler(.cancel)
                if ["https", "mailto", "tel"].contains(url.scheme?.lowercased() ?? "") {
                    DispatchQueue.main.async {
                        UIApplication.shared.open(url)
                    }
                }
            }
        }
    }
}
