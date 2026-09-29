import AppKit

@main struct RenderIconOptions {
  static func main() throws {
    let destination = URL(fileURLWithPath: CommandLine.arguments[1])
    try FileManager.default.createDirectory(at: destination, withIntermediateDirectories: true)
    let options = [
      ("sun.max", "1 · Sun"), ("sun.horizon", "2 · Horizon"),
      ("sun.haze", "3 · Corona"), ("circle.lefthalf.filled", "4 · Duotone disc"),
      ("circle.dotted", "5 · Rotating ring"),
    ]
    let canvas = NSImage(size: NSSize(width: 1000, height: 290))
    canvas.lockFocus()
    NSColor(calibratedWhite: 0.96, alpha: 1).setFill()
    NSRect(x: 0, y: 145, width: 1000, height: 145).fill()
    NSColor(calibratedWhite: 0.10, alpha: 1).setFill()
    NSRect(x: 0, y: 0, width: 1000, height: 145).fill()
    for (index, item) in options.enumerated() {
      guard let symbol = NSImage(systemSymbolName: item.0, accessibilityDescription: item.1),
        let image = symbol.withSymbolConfiguration(.init(pointSize: 16, weight: .regular))
      else { fatalError("Native SF Symbol unavailable: \(item.0)") }
      for dark in [false, true] {
        let colour: NSColor = dark ? .white : .black
        let tinted = image.withSymbolConfiguration(.init(paletteColors: [colour]))!
        let x = CGFloat(index) * 200 + 100
        let y: CGFloat = dark ? 90 : 235
        let ratio = min(18 / tinted.size.width, 18 / tinted.size.height)
        let size = NSSize(width: tinted.size.width * ratio, height: tinted.size.height * ratio)
        tinted.draw(
          in: NSRect(
            x: x - size.width / 2, y: y - size.height / 2,
            width: size.width, height: size.height))
        let title: [NSAttributedString.Key: Any] = [
          .font: NSFont.systemFont(ofSize: 13), .foregroundColor: colour,
        ]
        let text = NSAttributedString(string: item.1, attributes: title)
        text.draw(at: NSPoint(x: x - text.size().width / 2, y: y - 43))
        let name = NSAttributedString(
          string: item.0,
          attributes: [
            .font: NSFont.monospacedSystemFont(ofSize: 10, weight: .regular),
            .foregroundColor: colour.withAlphaComponent(0.6),
          ])
        name.draw(at: NSPoint(x: x - name.size().width / 2, y: y - 62))
      }
    }
    canvas.unlockFocus()
    let rep = NSBitmapImageRep(data: canvas.tiffRepresentation!)!
    try rep.representation(using: .png, properties: [:])!.write(
      to: destination.appendingPathComponent("menu-bar-icons.png"))
    print("Five native SF Symbols rendered")
  }
}
