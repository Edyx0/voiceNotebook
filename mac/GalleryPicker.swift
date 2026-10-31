import AppKit
import PhotosUI
import SwiftUI
import WebKit

// The system picker shares only the images the user selects.
struct GalleryPickerView: View {
    @State private var presented = false
    @State private var selection: [PhotosPickerItem] = []
    @State private var loading = false
    let finish: ([[String: String]]?, String?) -> Void

    var body: some View {
        VStack(spacing: 12) {
            if loading { ProgressView("Preparing photos…") }
            else { Text("Opening Photos…") }
        }
        .frame(width: 260, height: 110)
        .photosPicker(isPresented: $presented, selection: $selection, maxSelectionCount: 20, matching: .images)
        .onAppear { presented = true }
        .onChange(of: presented) { isPresented in
            if !isPresented {
                if selection.isEmpty { finish(nil, nil) }
                else { loadSelection() }
            }
        }
    }

    private func loadSelection() {
        guard !loading else { return }
        loading = true
        Task {
            do {
                var photos: [[String: String]] = []
                var total = 0
                for (index, item) in selection.enumerated() {
                    guard let data = try await item.loadTransferable(type: Data.self),
                          let image = NSImage(data: data),
                          let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil),
                          let jpeg = NSBitmapImageRep(cgImage: cg).representation(using: .jpeg, properties: [.compressionFactor: 0.92]),
                          jpeg.count <= 20_000_000 else {
                        throw NSError(domain: "GalleryPicker", code: 1, userInfo: [NSLocalizedDescriptionKey: "A selected photo could not be opened or is over 20 MB."])
                    }
                    total += jpeg.count
                    guard total <= 50_000_000 else {
                        throw NSError(domain: "GalleryPicker", code: 2, userInfo: [NSLocalizedDescriptionKey: "Choose fewer photos at a time (up to 50 MB)."])
                    }
                    photos.append(["name": "Photo \(index + 1).jpg", "data": jpeg.base64EncodedString()])
                }
                finish(photos, nil)
            } catch { finish(nil, error.localizedDescription) }
        }
    }
}

final class GalleryPicker {
    private var panel: NSPanel?

    func show(in parent: NSWindow, target: WKWebView) {
        guard panel == nil else { return }
        let panel = NSPanel(contentRect: .zero, styleMask: [.titled], backing: .buffered, defer: false)
        self.panel = panel
        panel.title = "Photos"
        panel.contentViewController = NSHostingController(rootView: GalleryPickerView { [weak self, weak target, weak panel, weak parent] photos, error in
            if let panel, let parent { parent.endSheet(panel) }
            self?.panel = nil
            guard let target, photos != nil || error != nil,
                  let data = try? JSONSerialization.data(withJSONObject: ["photos": photos ?? [], "error": error ?? ""]),
                  let json = String(data: data, encoding: .utf8) else { return }
            target.evaluateJavaScript("window.voiceNotebookGallerySelected?.(\(json))")
        })
        parent.beginSheet(panel)
    }
}
