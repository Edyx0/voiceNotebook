import AppKit

let target = CommandLine.arguments[1]
let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: 1024, pixelsHigh: 1024, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: bitmap)
NSColor(srgbRed: 64/255, green: 64/255, blue: 64/255, alpha: 1).setFill()
NSBezierPath(roundedRect: NSRect(x: 32, y: 32, width: 960, height: 960), xRadius: 216, yRadius: 216).fill()
let flip = NSAffineTransform()
flip.translateX(by: 0, yBy: 1024)
flip.scaleX(by: 1, yBy: -1)
flip.concat()
NSColor.white.setFill()
NSBezierPath(roundedRect: NSRect(x: 228, y: 156, width: 568, height: 712), xRadius: 68, yRadius: 68).fill()
NSColor(srgbRed: 191/255, green: 191/255, blue: 191/255, alpha: 1).setFill()
NSBezierPath(rect: NSRect(x: 351, y: 156, width: 18, height: 712)).fill()
NSColor(srgbRed: 64/255, green: 64/255, blue: 64/255, alpha: 1).setStroke()
let waveform = NSBezierPath()
waveform.lineWidth = 44
waveform.lineCapStyle = .round
let bars: [(CGFloat, CGFloat, CGFloat)] = [(450, 580, 444), (558, 636, 348), (666, 550, 468)]
for (x, start, end) in bars {
    waveform.move(to: NSPoint(x: x, y: start))
    waveform.line(to: NSPoint(x: x, y: end))
}
waveform.stroke()
NSColor(srgbRed: 217/255, green: 48/255, blue: 46/255, alpha: 1).setFill()
NSBezierPath(rect: NSRect(x: 228, y: 263, width: 132, height: 58)).fill()
NSColor(srgbRed: 230/255, green: 230/255, blue: 50/255, alpha: 1).setFill()
NSBezierPath(rect: NSRect(x: 435, y: 735, width: 249, height: 24)).fill()
NSGraphicsContext.restoreGraphicsState()
if CommandLine.arguments.count > 2 {
    try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[2]))
}
let iconset = URL(fileURLWithPath: NSTemporaryDirectory()).appendingPathComponent("voiceNotebook-\(UUID().uuidString).iconset")
try FileManager.default.createDirectory(at: iconset, withIntermediateDirectories: true)
for size in [16,32,128,256,512] {
    for scale in [1,2] {
        let px = size * scale
        let image = NSImage(size: NSSize(width: px, height: px))
        image.lockFocus()
        bitmap.draw(in: NSRect(x: 0, y: 0, width: px, height: px))
        let small = NSBitmapImageRep(focusedViewRect: NSRect(x: 0,y: 0,width: px,height: px))!
        image.unlockFocus()
        let suffix = scale == 2 ? "@2x" : ""
        try small.representation(using: .png, properties: [:])!.write(to: iconset.appendingPathComponent("icon_\(size)x\(size)\(suffix).png"))
    }
}
let process = Process()
process.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
process.arguments = ["-c","icns",iconset.path,"-o",target]
try process.run()
process.waitUntilExit()
try? FileManager.default.removeItem(at: iconset)
if process.terminationStatus != 0 { exit(1) }
