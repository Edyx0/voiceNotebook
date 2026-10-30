import AppKit
import Vision

// Preserve the approved photo and add local OCR when NotebookLM rejects an image-only source.
func makePhotoDocument(imagePath: String, outputPath: String) {
    do {
        let url = URL(fileURLWithPath: imagePath)
        guard let image = NSImage(contentsOf: url),
              let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
            throw NSError(domain: "PhotoDocument", code: 1, userInfo: [NSLocalizedDescriptionKey: "The approved photo could not be opened."])
        }
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let supported = try request.supportedRecognitionLanguages()
        request.recognitionLanguages = ["tr-TR", "en-US"].filter { supported.contains($0) }
        try VNImageRequestHandler(url: url).perform([request])
        let lines = (request.results ?? []).sorted { $0.boundingBox.midY > $1.boundingBox.midY }
            .compactMap { $0.topCandidates(1).first?.string }
        let data = NSMutableData()
        var imageBox = CGRect(x: 0, y: 0, width: cgImage.width, height: cgImage.height)
        guard let consumer = CGDataConsumer(data: data),
              let context = CGContext(consumer: consumer, mediaBox: &imageBox, nil) else {
            throw NSError(domain: "PhotoDocument", code: 3)
        }
        context.beginPDFPage(nil)
        context.draw(cgImage, in: imageBox)
        context.endPDFPage()

        if !lines.isEmpty {
        let paragraph = NSMutableParagraphStyle()
        paragraph.lineBreakMode = .byWordWrapping
        let text = NSAttributedString(string: "Local automatic text recognition may contain errors. The original photo is on page 1.\n\n" + lines.joined(separator: "\n"),
            attributes: [.font: NSFont.systemFont(ofSize: 12), .foregroundColor: NSColor.black, .paragraphStyle: paragraph])
        let height = text.boundingRect(with: NSSize(width: 515, height: CGFloat.greatestFiniteMagnitude), options: [.usesLineFragmentOrigin, .usesFontLeading]).height
        var textBox = CGRect(x: 0, y: 0, width: 595, height: max(842, ceil(height) + 80))
        let mediaBox = NSData(bytes: &textBox, length: MemoryLayout<CGRect>.size)
        context.beginPDFPage([kCGPDFContextMediaBox as String: mediaBox] as CFDictionary)
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(cgContext: context, flipped: false)
        text.draw(with: NSRect(x: 40, y: 40, width: 515, height: textBox.height - 80), options: [.usesLineFragmentOrigin, .usesFontLeading])
        NSGraphicsContext.restoreGraphicsState()
        context.endPDFPage()
        }
        context.closePDF()
        try (data as Data).write(to: URL(fileURLWithPath: outputPath), options: .atomic)
    } catch {
        FileHandle.standardError.write(Data(error.localizedDescription.utf8))
        exit(1)
    }
}
