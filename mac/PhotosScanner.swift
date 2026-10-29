import AppKit
import Photos
import Vision
import CryptoKit

func photosAccessState() -> String {
    switch PHPhotoLibrary.authorizationStatus(for: .readWrite) {
    case .authorized: return "authorized"
    case .limited: return "limited"
    case .notDetermined: return "notDetermined"
    case .denied: return "denied"
    case .restricted: return "restricted"
    @unknown default: return "unavailable"
    }
}

func requestPhotosAccess(completion: @escaping () -> Void) {
    if PHPhotoLibrary.authorizationStatus(for: .readWrite) == .notDetermined {
        PHPhotoLibrary.requestAuthorization(for: .readWrite) { _ in DispatchQueue.main.async(execute: completion) }
    } else {
        NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Photos")!)
        completion()
    }
}

// Runs inside the signed Mac app so Photos access belongs to voiceNotebook.
func scanClassPhotos(requestPath: String, responsePath: String) {
    DispatchQueue.global(qos: .userInitiated).async {
        var response: [String: Any] = [:]
        do {
            let request = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: requestPath))) as? [String: Any]
            guard let windows = request?["windows"] as? [[String: Any]],
                  let folder = request?["folder"] as? String,
                  let first = windows.compactMap({ $0["start"] as? Double }).min(),
                  let last = windows.compactMap({ $0["end"] as? Double }).max() else {
                throw NSError(domain: "Photos", code: 1, userInfo: [NSLocalizedDescriptionKey: "No uploaded classes are available to match photos."])
            }
            let authorization = PHPhotoLibrary.authorizationStatus(for: .readWrite)
            guard authorization == .authorized || authorization == .limited else {
                throw NSError(domain: "Photos", code: 2, userInfo: [NSLocalizedDescriptionKey: "Photos access is off. Allow voiceNotebook in System Settings → Privacy & Security → Photos, then try again."])
            }
            let options = PHFetchOptions()
            options.predicate = NSPredicate(format: "creationDate >= %@ AND creationDate < %@", Date(timeIntervalSince1970: first) as NSDate, Date(timeIntervalSince1970: last) as NSDate)
            options.sortDescriptors = [NSSortDescriptor(key: "creationDate", ascending: false)]
            let assets = PHAsset.fetchAssets(with: .image, options: options)
            let manager = PHImageManager.default()
            let imageOptions = PHImageRequestOptions()
            imageOptions.isSynchronous = true
            imageOptions.isNetworkAccessAllowed = true
            imageOptions.deliveryMode = .highQualityFormat
            imageOptions.resizeMode = .exact
            var photos: [[String: Any]] = []
            var unavailable = 0
            assets.enumerateObjects { asset, _, _ in
                autoreleasepool {
                    guard let captured = asset.creationDate, windows.contains(where: { window in
                        guard let start = window["start"] as? Double, let end = window["end"] as? Double else { return false }
                        return start <= captured.timeIntervalSince1970 && captured.timeIntervalSince1970 < end
                    }) else { return }
                    let id = SHA256.hash(data: Data(asset.localIdentifier.utf8)).map { String(format: "%02x", $0) }.joined()
                    let url = URL(fileURLWithPath: folder).appendingPathComponent("\(id).jpg")
                    // Never replace the exact image the user has already reviewed.
                    if !FileManager.default.fileExists(atPath: url.path) {
                        var jpeg: Data?
                        manager.requestImage(for: asset, targetSize: CGSize(width: 2400, height: 2400), contentMode: .aspectFit, options: imageOptions) { image, info in
                            guard (info?[PHImageResultIsDegradedKey] as? Bool) != true,
                                  let image = image,
                                  let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else { return }
                            jpeg = NSBitmapImageRep(cgImage: cg).representation(using: .jpeg, properties: [.compressionFactor: 0.9])
                        }
                        guard let jpeg else { unavailable += 1; return }
                        do { try jpeg.write(to: url, options: .atomic) }
                        catch { unavailable += 1; return }
                    }
                    var label = "In-class photo · check the board or slide"
                    let text = VNRecognizeTextRequest()
                    text.recognitionLevel = .fast
                    text.usesLanguageCorrection = false
                    if (try? VNImageRequestHandler(url: url).perform([text])) != nil {
                        let count = (text.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ").count
                        if count >= 25 { label = "Text detected · possible board or presentation" }
                    }
                    photos.append(["id": id, "captured_at": ISO8601DateFormatter().string(from: captured), "label": label])
                }
            }
            response = ["photos": photos, "unavailable": unavailable]
        } catch { response = ["error": error.localizedDescription] }
        do {
            try JSONSerialization.data(withJSONObject: response).write(to: URL(fileURLWithPath: responsePath), options: .atomic)
            exit(0)
        } catch { exit(1) }
    }
    dispatchMain()
}
