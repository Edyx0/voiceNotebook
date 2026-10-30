import AppKit

let target = CommandLine.arguments[1]
let source = URL(fileURLWithPath: "assets/brand/app-icon.png")
let bitmap = NSBitmapImageRep(data: try Data(contentsOf: source))!
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
