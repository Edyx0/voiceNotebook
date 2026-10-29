import AppKit
import AuthenticationServices

/// The system's browser authentication popup has no browser tabs or normal toolbar.
final class GoogleSignIn: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession?
    private weak var anchor: NSWindow?
    var onFailure: ((String) -> Void)?
    var onClosed: (() -> Void)?
    private var attempt: UUID?

    func start(in window: NSWindow) -> Bool {
        close()
        let currentAttempt = UUID()
        attempt = currentAttempt
        anchor = window
        let url = URL(string: "https://accounts.google.com/AccountChooser?continue=https%3A%2F%2Fnotebook.google.com%2F")!
        let authentication = ASWebAuthenticationSession(url: url, callbackURLScheme: "voicenotebook") { [weak self] _, error in
            DispatchQueue.main.async {
                guard let self, self.attempt == currentAttempt else { return }
                self.session = nil
                self.attempt = nil
                if let error = error as NSError?,
                   !(error.domain == ASWebAuthenticationSessionError.errorDomain && error.code == ASWebAuthenticationSessionError.canceledLogin.rawValue) {
                    self.onFailure?(error.localizedDescription)
                } else {
                    self.onClosed?()
                }
            }
        }
        authentication.presentationContextProvider = self
        authentication.prefersEphemeralWebBrowserSession = false
        session = authentication
        if authentication.start() { return true }
        session = nil
        attempt = nil
        return false
    }

    func close() {
        attempt = nil
        session?.cancel()
        session = nil
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        anchor ?? NSApp.mainWindow ?? ASPresentationAnchor()
    }
}
