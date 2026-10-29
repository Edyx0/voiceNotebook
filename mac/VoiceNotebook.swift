import AppKit
import WebKit

final class AppDelegate: NSObject, NSApplicationDelegate, WKNavigationDelegate, WKUIDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var webView: WKWebView!
    var settingsWindow: NSWindow?
    var settingsWebView: WKWebView?
    var backend: Process?
    var readyURL: URL!
    var baseURL: URL?
    var launchTimer: Timer?
    var attempts = 0
    var logHandle: FileHandle?
    private let googleSignIn = GoogleSignIn()

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildMenu()
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1160, height: 820), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "voiceNotebook"
        window.minSize = NSSize(width: 780, height: 600)
        window.center()
        window.setFrameAutosaveName("MainWindow")
        let config = WKWebViewConfiguration()
        config.userContentController.add(self, name: "native")
        webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = self
        webView.uiDelegate = self
        webView.setValue(false, forKey: "drawsBackground")
        window.contentView = webView
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        startBackend()
    }

    func buildMenu() {
        let menu = NSMenu()
        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "About voiceNotebook", action: #selector(about), keyEquivalent: "")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Settings…", action: #selector(settings), keyEquivalent: ",")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "Hide voiceNotebook", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        appMenu.addItem(withTitle: "Quit voiceNotebook", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        menu.addItem(appItem)
        let fileItem = NSMenuItem()
        let fileMenu = NSMenu(title: "File")
        fileMenu.addItem(withTitle: "Scan Recordings", action: #selector(scan), keyEquivalent: "r")
        fileMenu.addItem(withTitle: "Choose Recordings Folder…", action: #selector(chooseFolder), keyEquivalent: "o")
        fileItem.submenu = fileMenu
        menu.addItem(fileItem)
        let editItem = NSMenuItem()
        let edit = NSMenu(title: "Edit")
        for (title, selector, key) in [("Undo", "undo:", "z"), ("Cut", "cut:", "x"), ("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            edit.addItem(withTitle: title, action: Selector(selector), keyEquivalent: key)
        }
        editItem.submenu = edit
        menu.addItem(editItem)
        let viewItem = NSMenuItem()
        let viewMenu = NSMenu(title: "View")
        viewMenu.addItem(withTitle: "Zoom In", action: #selector(zoomIn), keyEquivalent: "+")
        viewMenu.addItem(withTitle: "Zoom Out", action: #selector(zoomOut), keyEquivalent: "-")
        viewMenu.addItem(withTitle: "Actual Size", action: #selector(actualSize), keyEquivalent: "0")
        viewItem.submenu = viewMenu
        menu.addItem(viewItem)
        let helpItem = NSMenuItem()
        let help = NSMenu(title: "Help")
        help.addItem(withTitle: "NotebookLM Connection", action: #selector(connection), keyEquivalent: "")
        help.addItem(withTitle: "Voice Memos Access…", action: #selector(settings), keyEquivalent: "")
        help.addItem(withTitle: "Show Local Data", action: #selector(showData), keyEquivalent: "")
        helpItem.submenu = help
        menu.addItem(helpItem)
        NSApp.mainMenu = menu
    }

    func startBackend() {
        guard let resources = Bundle.main.resourceURL else { return }
        let executable = resources.appendingPathComponent("backend/voice-notebook-server")
        readyURL = FileManager.default.temporaryDirectory.appendingPathComponent("voiceNotebook-\(UUID().uuidString).json")
        let logDirectory = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/voiceNotebook")
        try? FileManager.default.createDirectory(at: logDirectory, withIntermediateDirectories: true)
        let logURL = logDirectory.appendingPathComponent("app.log")
        FileManager.default.createFile(atPath: logURL.path, contents: nil)
        logHandle = try? FileHandle(forWritingTo: logURL)
        let process = Process()
        process.executableURL = executable
        process.arguments = ["--port", "0", "--ready-file", readyURL.path]
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        env["VOICE_NOTEBOOK_PHOTOS_HELPER"] = Bundle.main.executableURL?.path
        process.environment = env
        process.standardOutput = logHandle
        process.standardError = logHandle
        backend = process
        do {
            try process.run()
            launchTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in self?.checkReady() }
        } catch { showError("The local service could not start. \(error.localizedDescription)") }
    }

    func checkReady() {
        attempts += 1
        if let data = try? Data(contentsOf: readyURL), let info = try? JSONSerialization.jsonObject(with: data) as? [String: String], let raw = info["url"], let url = URL(string: raw) {
            launchTimer?.invalidate()
            baseURL = url
            webView.load(URLRequest(url: url))
            try? FileManager.default.removeItem(at: readyURL)
        } else if backend?.isRunning == false || attempts > 600 {
            launchTimer?.invalidate()
            showError("The local service could not start. If voiceNotebook is already running in a terminal, stop that copy and reopen this app. Logs are in ~/Library/Logs/voiceNotebook/app.log.")
        }
    }

    func showError(_ message: String) {
        let alert = NSAlert()
        alert.messageText = "voiceNotebook couldn’t open"
        alert.informativeText = message
        alert.runModal()
        NSApp.terminate(nil)
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard message.frameInfo.isMainFrame, message.frameInfo.request.url?.host == "127.0.0.1", message.frameInfo.request.url?.port == baseURL?.port,
              let body = message.body as? [String: String] else { return }
        switch body["action"] {
        case "settings": settings()
        case "chooseFolder": presentFolderChooser(in: message.webView ?? webView)
        case "fullDiskAccess": fullDiskAccess()
        case "showData": showData()
        case "photosAccess": requestPhotosAccess { [weak self] in self?.refreshAccess() }
        case "refreshAccess": refreshAccess()
        case "showApplication": NSWorkspace.shared.activateFileViewerSelecting([Bundle.main.bundleURL])
        case "googleSignInConnected":
            NSApp.activate(ignoringOtherApps: true)
            (message.webView?.window ?? window).makeKeyAndOrderFront(nil)
        case "googleSignIn":
            googleSignIn.onClosed = { [weak content = message.webView] in
                content?.evaluateJavaScript("window.finishGoogleSignIn?.()")
            }
            googleSignIn.onFailure = { [weak content = message.webView] error in
                guard let data = try? JSONSerialization.data(withJSONObject: [error]),
                      let json = String(data: data, encoding: .utf8) else { return }
                content?.evaluateJavaScript("action('/api/login/cancel', {}).then(() => notice(\(json)[0], true))")
            }
            if !googleSignIn.start(in: message.webView?.window ?? window) {
                message.webView?.evaluateJavaScript("action('/api/login/cancel', {}).then(() => notice('Could not open Google sign-in.', true))")
            }
        case "closeGoogleSignIn": googleSignIn.close()
        default: break
        }
    }

    @objc func chooseFolder() {
        settings()
        guard let settingsWebView else { return }
        presentFolderChooser(in: settingsWebView)
    }

    func presentFolderChooser(in target: WKWebView) {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Use Folder"
        panel.message = "Choose Voice Memos recordings or a folder of exported audio."
        guard let parent = target.window else { return }
        panel.beginSheetModal(for: parent) { response in
            guard response == .OK, let path = panel.url?.path,
                  let encoded = try? JSONSerialization.data(withJSONObject: [path]), let json = String(data: encoded, encoding: .utf8) else { return }
            target.evaluateJavaScript("window.voiceNotebookFolderChosen(\(json)[0])")
        }
    }

    @objc func fullDiskAccess() {
        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles")!)
    }
    func refreshAccess() {
        webView?.evaluateJavaScript("window.refreshAccess?.()")
        settingsWebView?.evaluateJavaScript("window.refreshAccess?.()")
    }
    func applicationDidBecomeActive(_ notification: Notification) { refreshAccess() }
    @objc func showData() {
        NSWorkspace.shared.open(FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/voiceNotebook"))
    }
    @objc func scan() { webView.evaluateJavaScript("document.getElementById('scan').click()") }
    @objc func zoomIn() { webView.pageZoom = min(2.5, webView.pageZoom + 0.1) }
    @objc func zoomOut() { webView.pageZoom = max(0.7, webView.pageZoom - 0.1) }
    @objc func actualSize() { webView.pageZoom = 1 }
    @objc func settings() {
        guard let baseURL else { return }
        if let settingsWindow {
            settingsWindow.makeKeyAndOrderFront(nil)
            settingsWebView?.evaluateJavaScript("window.refreshAccess?.()")
            return
        }
        let configuration = WKWebViewConfiguration()
        configuration.userContentController.add(self, name: "native")
        let content = WKWebView(frame: .zero, configuration: configuration)
        content.navigationDelegate = self
        content.uiDelegate = self
        let panel = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 640, height: 770), styleMask: [.titled, .closable], backing: .buffered, defer: false)
        panel.title = "Settings"
        panel.isReleasedWhenClosed = false
        panel.contentView = content
        panel.center()
        panel.setFrameAutosaveName("SettingsWindow")
        settingsWindow = panel
        settingsWebView = content
        var components = URLComponents(url: baseURL, resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "settings", value: "1")]
        if let url = components.url { content.load(URLRequest(url: url)) }
        panel.makeKeyAndOrderFront(nil)
    }
    @objc func connection() { webView.evaluateJavaScript("view('connection')") }
    @objc func about() {
        NSApp.orderFrontStandardAboutPanel(options: [.applicationName: "voiceNotebook", .applicationVersion: "1.0", .credits: NSAttributedString(string: "Voice Memos → MP3 → weekly NotebookLM notebooks.\nNotebookLM integration uses the unofficial notebooklm-py client.")])
    }

    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        guard let url = navigationAction.request.url else { decisionHandler(.cancel); return }
        if url.host == "127.0.0.1" && url.port == baseURL?.port { decisionHandler(.allow) }
        else {
            if url.scheme == "https" { NSWorkspace.shared.open(url) }
            decisionHandler(.cancel)
        }
    }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration, for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, url.scheme == "https" { NSWorkspace.shared.open(url) }
        return nil
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters, initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowsMultipleSelection = false
        panel.allowedFileTypes = ["jpg", "jpeg", "png", "heic", "heif", "tiff", "bmp"]
        panel.prompt = "Read Timetable"
        panel.beginSheetModal(for: window) { response in completionHandler(response == .OK ? panel.urls : nil) }
    }
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        guard let baseURL, backend?.isRunning == true else { return .terminateNow }
        var request = URLRequest(url: baseURL.appendingPathComponent("api/state"))
        request.timeoutInterval = 2
        URLSession.shared.dataTask(with: request) { data, _, _ in
            let state = data.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] }
            let busy = (state?["job"] as? [String: Any])?["busy"] as? Bool ?? false
            let auth = (state?["auth"] as? [String: Any])?["status"] as? String
            DispatchQueue.main.async {
                if busy || auth == "signing_in" {
                    let alert = NSAlert()
                    alert.messageText = "Quit while an operation is running?"
                    alert.informativeText = "The current operation will stop. Saved upload progress will be available when you reopen the app."
                    alert.addButton(withTitle: "Keep Running")
                    alert.addButton(withTitle: "Quit")
                    NSApp.reply(toApplicationShouldTerminate: alert.runModal() == .alertSecondButtonReturn)
                } else { NSApp.reply(toApplicationShouldTerminate: true) }
            }
        }.resume()
        return .terminateLater
    }
    func applicationWillTerminate(_ notification: Notification) {
        googleSignIn.close()
        launchTimer?.invalidate()
        if backend?.isRunning == true { backend?.terminate() }
        if let readyURL { try? FileManager.default.removeItem(at: readyURL) }
        try? logHandle?.close()
    }
}

@main
struct VoiceNotebookMain {
    static func main() {
        if CommandLine.arguments.count == 2 && CommandLine.arguments[1] == "--permissions" {
            let data = try! JSONSerialization.data(withJSONObject: ["photos":photosAccessState()])
            FileHandle.standardOutput.write(data)
            return
        }
        if CommandLine.arguments.count == 4 && CommandLine.arguments[1] == "--scan-photos" {
            scanClassPhotos(requestPath: CommandLine.arguments[2], responsePath: CommandLine.arguments[3])
            exit(0)
        }
        if CommandLine.arguments.count == 4 && CommandLine.arguments[1] == "--photo-document" {
            makePhotoDocument(imagePath: CommandLine.arguments[2], outputPath: CommandLine.arguments[3])
            return
        }
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.setActivationPolicy(.regular)
        app.delegate = delegate
        app.run()
    }
}
