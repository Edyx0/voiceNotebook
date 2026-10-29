import Foundation
import Vision
import ImageIO

do {
    guard CommandLine.arguments.count == 2 else { throw NSError(domain: "Timetable", code: 1, userInfo: [NSLocalizedDescriptionKey:"Choose a timetable image."]) }
    let image = URL(fileURLWithPath: CommandLine.arguments[1])
    guard let source = CGImageSourceCreateWithURL(image as CFURL, nil), CGImageSourceGetCount(source) > 0 else {
        throw NSError(domain: "Timetable", code: 2, userInfo: [NSLocalizedDescriptionKey:"This image could not be opened. Try a JPEG, PNG or HEIC photo."])
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false  // Keep course codes intact.
    request.automaticallyDetectsLanguage = true
    let supported = try request.supportedRecognitionLanguages()
    request.recognitionLanguages = ["en-US", "tr-TR"].filter { supported.contains($0) }
    var results: [(text: VNRecognizedText, box: CGRect)] = []
    // Narrow passes recover table cells missed beside identical neighboring text.
    for region in [CGRect(x: 0, y: 0, width: 1, height: 1),
                   CGRect(x: 0, y: 0, width: 0.5, height: 1),
                   CGRect(x: 0.5, y: 0, width: 0.5, height: 1)] {
        request.regionOfInterest = region
        try VNImageRequestHandler(url: image, options: [:]).perform([request])
        for item in request.results ?? [] {
            guard let text = item.topCandidates(1).first else { continue }
            let local = item.boundingBox
            let box = CGRect(x: region.minX + local.minX * region.width,
                             y: region.minY + local.minY * region.height,
                             width: local.width * region.width, height: local.height * region.height)
            if !results.contains(where: { $0.box.intersection(box).width > min($0.box.width, box.width) * 0.5
                && $0.box.intersection(box).height > min($0.box.height, box.height) * 0.5 }) {
                results.append((text, box))
            }
        }
    }
    let observations: [[String: Any]] = results.map { item in
        let text = item.text
        let box = item.box
        return ["text":text.string, "confidence":text.confidence,
                "x":box.minX, "y":1-box.maxY, "width":box.width, "height":box.height]
    }
    let data = try JSONSerialization.data(withJSONObject: ["observations":observations])
    FileHandle.standardOutput.write(data)
} catch {
    FileHandle.standardError.write(Data(error.localizedDescription.utf8))
    exit(1)
}
