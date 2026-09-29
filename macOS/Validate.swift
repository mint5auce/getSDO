import AppKit
import MetalKit
import ScreenSaver

@objc protocol CapturableSaver {
  func captureFrame(_ path: String, atTime time: Double)
}
@main struct Validate {
  static func main() throws {
    let app = NSApplication.shared
    app.setActivationPolicy(.accessory)
    let output = URL(fileURLWithPath: CommandLine.arguments[1])
    try FileManager.default.createDirectory(at: output, withIntermediateDirectories: true)
    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 1000, height: 650), styleMask: [.titled],
      backing: .buffered, defer: false)
    window.title = "Solar Horizon validation"
    let view = MTKView(frame: NSRect(x: 0, y: 0, width: 1000, height: 650))
    window.contentView = view
    let renderer = try SolarRenderer(view: view)
    view.isPaused = true
    view.framebufferOnly = false
    window.orderFront(nil)
    RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.2))
    guard renderer.texture != nil else { fatalError(renderer.fault ?? "No scene") }
    renderer.phaseOffset = 0
    renderer.frozenAngle = nil
    renderer.viewMode = .horizon
    for time in [0.0, 300, 600, 900, 1200] {
      renderer.render(
        in: view, at: time, capture: output.appendingPathComponent("metal-\(Int(time)).png"))
    }
    guard let bundle = Bundle(path: CommandLine.arguments[2]), bundle.load(),
      let saverType = bundle.principalClass as? ScreenSaverView.Type,
      let saver = saverType.init(frame: .zero, isPreview: true)
    else { fatalError("Saver could not load") }
    window.contentView = saver
    saver.frame = view.frame
    // Reproduce Settings: empty initial frame, attach and resize, no startAnimation.
    RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.2))
    guard saver.value(forKey: "sceneLoaded") as? Bool == true else {
      fatalError("Saver scene could not load: \(saver.value(forKey:"sceneFault") ?? "unknown")")
    }
    // Both binaries render the same scene at the exact same continuous clock time.
    let selector = NSSelectorFromString("captureFrame:atTime:")
    guard saver.responds(to: selector) else { fatalError("Capture method missing") }
    let modeSelector = NSSelectorFromString("captureFrame:atTime:viewMode:")
    guard saver.responds(to: modeSelector) else { fatalError("Mode capture method missing") }
    typealias ModeCapture = @convention(c) (AnyObject, Selector, NSString, Double, NSString) -> Void
    let captureMode = unsafeBitCast(saver.method(for: modeSelector), to: ModeCapture.self)
    let capture: (AnyObject, Selector, NSString, Double) -> Void = { object, _, path, time in
      captureMode(object, modeSelector, path, time, SolarViewMode.horizon.rawValue as NSString)
    }
    for time in [0.0, 300, 600, 900, 1200] {
      captureMode(
        saver, modeSelector,
        output.appendingPathComponent("saver-\(Int(time)).png").path as NSString,
        time, SolarViewMode.horizon.rawValue as NSString)
    }
    saver.bounds = NSRect(x: 0, y: 0, width: 2000, height: 1300)
    capture(
      saver, selector, output.appendingPathComponent("retina-bounds.png").path as NSString, 600)
    saver.setBoundsSize(NSSize(width: 2000, height: 1300))
    capture(
      saver, selector, output.appendingPathComponent("retina-bounds-size.png").path as NSString, 600
    )
    saver.frame = NSRect(x: 0, y: 0, width: 2000, height: 1300)
    saver.bounds = NSRect(x: 0, y: 0, width: 2000, height: 1300)
    capture(
      saver, selector, output.appendingPathComponent("retina-frame.png").path as NSString, 600)
    saver.frame = NSRect(x: 0, y: 0, width: 1000, height: 650)
    saver.bounds = NSRect(x: 0, y: 0, width: 1000, height: 650)
    saver.startAnimation()
    saver.stopAnimation()
    // Snapshot the retained image after the host stops animation, as Settings does.
    window.setContentSize(NSSize(width: 640, height: 400))
    saver.frame = NSRect(x: 0, y: 0, width: 640, height: 400)
    RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.2))
    capture(
      saver, selector, output.appendingPathComponent("layer-preview.png").path as NSString, 600)
    for cycle in 0..<5 {
      window.contentView = nil
      saver.stopAnimation()
      window.contentView = saver
      saver.startAnimation()
      saver.stopAnimation()
      capture(
        saver, selector, output.appendingPathComponent("restart-\(cycle).png").path as NSString,
        600)
    }
    // Validate the new mode without changing the user's persisted playback state.
    // Use a full-size saver view in this window for physical-pixel comparisons.
    guard let surfaceSaver = saverType.init(frame: saver.frame, isPreview: false) else {
      fatalError("Surface saver could not load")
    }
    window.contentView = surfaceSaver
    window.setContentSize(NSSize(width: 1000, height: 650))
    surfaceSaver.frame = NSRect(x: 0, y: 0, width: 1000, height: 650)
    RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.2))
    for time in [0.0, 300, 600, 900, 1200] {
      captureMode(
        surfaceSaver, modeSelector,
        output.appendingPathComponent("surface-saver-\(Int(time)).png").path as NSString,
        time, SolarViewMode.surfaceScroll.rawValue as NSString)
    }
    surfaceSaver.bounds = NSRect(x: 0, y: 0, width: 2000, height: 1300)
    captureMode(
      surfaceSaver, modeSelector,
      output.appendingPathComponent("surface-retina-bounds.png").path as NSString,
      600, SolarViewMode.surfaceScroll.rawValue as NSString)
    surfaceSaver.frame = NSRect(x: 0, y: 0, width: 1000, height: 650)
    surfaceSaver.bounds = surfaceSaver.frame
    window.contentView = saver
    window.setContentSize(NSSize(width: 640, height: 400))
    saver.frame = NSRect(x: 0, y: 0, width: 640, height: 400)
    for time in [0.0, 300, 600, 900] {
      captureMode(
        saver, modeSelector,
        output.appendingPathComponent("surface-preview-\(Int(time)).png").path as NSString,
        time, SolarViewMode.surfaceScroll.rawValue as NSString)
    }
    window.contentView = view
    window.setContentSize(NSSize(width: 1000, height: 650))
    renderer.viewMode = .surfaceScroll
    for time in [0.0, 300, 600, 900, 1200] {
      renderer.render(
        in: view, at: time, capture: output.appendingPathComponent("surface-metal-\(Int(time)).png")
      )
    }
    let texture = renderer.texture!
    let nativePath = SolarSurfacePath(
      image: CGSize(width: texture.width, height: texture.height), viewport: view.drawableSize)
    var expected: [[String: Any]] = []
    for time in [0.0, 300, 600, 900] {
      let origin = nativePath.origin(at: Double(renderer.rotationAngle(at: time)))
      expected.append(["time": time, "x": origin.x, "y": origin.y])
    }
    try JSONSerialization.data(withJSONObject: [
      "texture": (renderer.scene!["current"] as! [String: Any])["texture"]!,
      "origins": expected,
    ]).write(to: output.appendingPathComponent("surface-crops.json"))
    window.contentView = surfaceSaver
    for time in [0.0, 300, 600, 900, 1200] {
      captureMode(
        surfaceSaver, modeSelector,
        output.appendingPathComponent("peek-saver-\(Int(time)).png").path as NSString,
        time, SolarViewMode.peek.rawValue as NSString)
    }
    surfaceSaver.bounds = NSRect(x: 0, y: 0, width: 2000, height: 1300)
    captureMode(
      surfaceSaver, modeSelector,
      output.appendingPathComponent("peek-retina-bounds.png").path as NSString,
      600, SolarViewMode.peek.rawValue as NSString)
    surfaceSaver.frame = NSRect(x: 0, y: 0, width: 1000, height: 650)
    surfaceSaver.bounds = surfaceSaver.frame
    window.contentView = saver
    window.setContentSize(NSSize(width: 640, height: 400))
    saver.frame = NSRect(x: 0, y: 0, width: 640, height: 400)
    for time in [0.0, 300, 600, 900] {
      captureMode(
        saver, modeSelector,
        output.appendingPathComponent("peek-preview-\(Int(time)).png").path as NSString,
        time, SolarViewMode.peek.rawValue as NSString)
    }
    for cycle in 0..<3 {
      window.contentView = nil
      saver.stopAnimation()
      window.contentView = saver
      saver.startAnimation()
      saver.stopAnimation()
      captureMode(
        saver, modeSelector,
        output.appendingPathComponent("peek-restart-\(cycle).png").path as NSString,
        600, SolarViewMode.peek.rawValue as NSString)
    }
    window.contentView = view
    window.setContentSize(NSSize(width: 1000, height: 650))
    renderer.viewMode = .peek
    for time in [0.0, 300, 600, 900, 1200] {
      renderer.render(
        in: view, at: time, capture: output.appendingPathComponent("peek-metal-\(Int(time)).png"))
    }
    let limb = (renderer.scene!["current"] as! [String: Any])["limb_uv"] as! Double
    let center = solarPeekCenter(
      viewport: view.drawableSize, limbRadius: CGFloat(texture.width) * limb)
    try JSONSerialization.data(withJSONObject: [
      "texture": (renderer.scene!["current"] as! [String: Any])["texture"]!,
      "center_x": center.x, "center_y": center.y,
      "limb_radius": CGFloat(texture.width) * limb,
    ]).write(to: output.appendingPathComponent("peek-geometry.json"))
    let referenceCenter = solarPeekCenter(
      viewport: CGSize(width: 1984, height: 1294), limbRadius: 1632)
    precondition(abs(referenceCenter.x - 2040) < 20 && abs(referenceCenter.y - 1160) < 20)
    validateSurfaceCoverage()
    for mode in SolarViewMode.allCases {
      let original: [String: Any] = [
        "view_mode": mode.rawValue, "phase_offset": 0.25, "future_setting": true,
      ]
      let paused = solarToggledPlayback(original, at: 123)
      let resumed = solarToggledPlayback(paused, at: 456)
      precondition(
        SolarViewMode(playback: paused) == mode && SolarViewMode(playback: resumed) == mode)
      precondition(resumed["paused_angle"] == nil && resumed["future_setting"] as? Bool == true)
      let pausedAngle = paused["paused_angle"] as! Double
      let resumedAngle = 456.0 / 1200 * 2 * Double.pi + (resumed["phase_offset"] as! Double)
      precondition(abs(pausedAngle - resumedAngle) < 0.000001)
    }
    window.setContentSize(NSSize(width: 1000, height: 650))
    let scenario = output.appendingPathComponent("scenario")
    try FileManager.default.createDirectory(at: scenario, withIntermediateDirectories: true)
    func solid(_ name: String, _ colour: NSColor) throws -> [String: Any] {
      let folder = scenario.appendingPathComponent("scenes/\(name)")
      try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
      let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: 64, pixelsHigh: 64, bitsPerSample: 8, samplesPerPixel: 4,
        hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 256,
        bitsPerPixel: 32)!
      let rgb = colour.usingColorSpace(.deviceRGB)!
      for pixel in 0..<64 * 64 {
        rep.bitmapData![pixel * 4] = UInt8((rgb.redComponent * 255).rounded())
        rep.bitmapData![pixel * 4 + 1] = UInt8((rgb.greenComponent * 255).rounded())
        rep.bitmapData![pixel * 4 + 2] = UInt8((rgb.blueComponent * 255).rounded())
        rep.bitmapData![pixel * 4 + 3] = 255
      }
      let url = folder.appendingPathComponent("texture.png")
      try rep.representation(using: .png, properties: [:])!.write(to: url)
      return ["id": name, "texture": url.path, "limb_uv": 0.4]
    }
    let red = try solid("red", .red)
    let blue = try solid("blue", .blue)
    let testScene: [String: Any] = [
      "current": blue, "previous": red, "transition_start": 100.0, "transition_seconds": 10.0,
    ]
    try JSONSerialization.data(withJSONObject: testScene).write(
      to: scenario.appendingPathComponent("scene.json"))
    window.contentView = view
    let crossfade = try SolarRenderer(view: view, support: scenario)
    view.isPaused = true
    view.framebufferOnly = false
    for time in [100.0, 105, 110] {
      crossfade.render(
        in: view, at: time, capture: output.appendingPathComponent("crossfade-\(Int(time)).png"))
    }
    window.close()
    print("All three view modes, full-image native scroll coverage and pause continuity verified")
  }

  static func validateSurfaceCoverage() {
    for viewport in [
      CGSize(width: 2940, height: 1912), CGSize(width: 1280, height: 800),
      CGSize(width: 1536, height: 2048), CGSize(width: 5120, height: 2880),
    ] {
      let path = SolarSurfacePath(image: CGSize(width: 4096, height: 4096), viewport: viewport)
      var covered = Set<Int>()
      for frame in 0..<3600 {
        let origin = path.origin(at: Double(frame) / 3600 * 2 * .pi)
        precondition(origin.x >= min(0, (4096 - viewport.width) / 2) - 0.001)
        precondition(origin.y >= min(0, (4096 - viewport.height) / 2) - 0.001)
        let minX = max(0, Int(ceil(origin.x / 64)))
        let maxX = min(63, Int(floor((origin.x + viewport.width) / 64)))
        let minY = max(0, Int(ceil(origin.y / 64)))
        let maxY = min(63, Int(floor((origin.y + viewport.height) / 64)))
        if minX <= maxX && minY <= maxY {
          for y in minY...maxY { for x in minX...maxX { covered.insert(y * 64 + x) } }
        }
      }
      precondition(covered.count == 4096, "Scroll missed part of the image at \(viewport)")
      precondition(path.origin(at: 0) == path.origin(at: 2 * .pi), "Scroll seam moved")
    }
  }
}
