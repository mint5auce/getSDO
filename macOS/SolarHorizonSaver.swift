import AppKit
import OSLog
import ScreenSaver

private let saverLog = Logger(subsystem: "uk.jonh.getSDO.saver", category: "lifecycle")

// Draw a retained image through AppKit, independent of remote Metal drawables.
@objc(SolarHorizonSaver)
final class SolarHorizonSaver: ScreenSaverView {
  private var currentImage: NSImage?
  private var previousImage: NSImage?
  private var scene: [String: Any]?
  private var sceneID = ""
  private var sceneError: String?
  private var frameTimer: Timer?
  private var frozenAngle: Float?
  private var phaseOffset: Float = 0
  private var viewMode: SolarViewMode = .horizon
  private var running = true
  private var stillTime = solarTime()
  private var nextCheck = 0.0
  private var frameInterval = 1.0 / 30

  deinit { frameTimer?.invalidate() }
  override var isOpaque: Bool { true }
  private var renderingBounds: NSRect {
    guard let window else { return bounds }
    let logical = window.contentLayoutRect.size
    let scale = window.backingScaleFactor
    // Legacy snapshots can replace both frame and bounds with backing pixels,
    // while the window and drawing context remain in logical coordinates.
    if scale > 1, logical.width > 0, logical.height > 0,
      abs(bounds.width - logical.width * scale) < 0.01,
      abs(bounds.height - logical.height * scale) < 0.01
    {
      return NSRect(origin: .zero, size: logical)
    }
    return bounds
  }
  override init?(frame: NSRect, isPreview: Bool) {
    let size =
      isPreview
      ? NSSize(width: 640, height: 400)
      : (NSScreen.main?.frame.size ?? NSSize(width: 1920, height: 1080))
    super.init(
      frame: frame.isEmpty ? NSRect(origin: .zero, size: size) : frame, isPreview: isPreview)
    setup()
  }
  required init?(coder: NSCoder) {
    super.init(coder: coder)
    setup()
  }
  private func setup() {
    wantsLayer = true
    autoresizingMask = [.width, .height]
    animationTimeInterval = 2
    reload()
    needsDisplay = true
    saverLog.notice("Setup AppKit preview=\(self.isPreview) loaded=\(self.sceneLoaded)")
  }
  override func viewDidMoveToWindow() {
    super.viewDidMoveToWindow()
    frameTimer?.invalidate()
    frameTimer = nil
    if window != nil {
      running = true
      startFrameClock()
    }
    needsDisplay = true
    saverLog.notice("Attached=\(self.window != nil) loaded=\(self.sceneLoaded)")
  }
  override func startAnimation() {
    super.startAnimation()
    running = true
    reload()
    startFrameClock()
    needsDisplay = true
    saverLog.notice("Start loaded=\(self.sceneLoaded)")
  }
  override func stopAnimation() {
    stillTime = solarTime()
    running = false
    frameTimer?.invalidate()
    frameTimer = nil
    // Settings can stop a view before requesting its snapshot.
    needsDisplay = true
    super.stopAnimation()
    saverLog.notice("Stop retained image=\(self.sceneLoaded)")
  }
  override func animateOneFrame() { needsDisplay = true }
  private func startFrameClock() {
    frameTimer?.invalidate()
    frameTimer = nil
    guard running, window != nil else { return }
    frameTimer = Timer.scheduledTimer(withTimeInterval: frameInterval, repeats: true) {
      [weak self] _ in self?.needsDisplay = true
    }
  }
  private func image(_ entry: [String: Any]?) throws -> NSImage? {
    guard let path = entry?["texture"] as? String else { return nil }
    let url = URL(fileURLWithPath: path).standardizedFileURL.resolvingSymlinksInPath()
    let allowed = solarSupport.appendingPathComponent("scenes").resolvingSymlinksInPath().path + "/"
    guard url.path.hasPrefix(allowed), let image = NSImage(contentsOf: url),
      let cg = image.cgImage(forProposedRect: nil, context: nil, hints: nil)
    else { throw NSError(domain: "SolarHorizon", code: 2) }
    image.size = NSSize(width: cg.width, height: cg.height)
    return image
  }
  private func reload() {
    nextCheck = solarTime() + 2
    let playback = readJSON("playback.json")
    viewMode = SolarViewMode(playback: playback)
    frozenAngle = (playback?["paused_angle"] as? Double).map { Float($0) }
    phaseOffset = Float(playback?["phase_offset"] as? Double ?? 0)
    let interval =
      frozenAngle != nil || NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
      ? 1.0 : 1.0 / 30
    if interval != frameInterval {
      frameInterval = interval
      startFrameClock()
    }
    guard let candidate = readJSON("scene.json"),
      let current = candidate["current"] as? [String: Any], let id = current["id"] as? String
    else {
      if scene == nil { sceneError = "Prepared scene is missing" }
      return
    }
    guard id != sceneID else { return }
    do {
      guard let next = try image(current) else { return }
      let old = try image(candidate["previous"] as? [String: Any])
      currentImage = next
      previousImage = old
      scene = candidate
      sceneID = id
      sceneError = nil
      saverLog.notice("Loaded AppKit scene \(id, privacy: .public)")
    } catch {
      sceneError = error.localizedDescription
      saverLog.error("Scene load failed: \(error.localizedDescription, privacy: .public)")
    }
  }
  override func draw(_ dirtyRect: NSRect) {
    if solarTime() >= nextCheck { reload() }
    drawScene(at: running ? solarTime() : stillTime)
  }
  private func drawScene(
    at now: Double, mode: SolarViewMode? = nil, angle captureAngle: Double? = nil
  ) {
    NSColor.black.setFill()
    let extent = renderingBounds
    extent.fill()
    guard let context = NSGraphicsContext.current, let image = currentImage,
      let current = scene?["current"] as? [String: Any]
    else { return }
    let angle =
      captureAngle
      ?? Double(
        solarRotationAngle(at: now, frozenAngle: frozenAngle, phaseOffset: phaseOffset))
    func band(_ image: NSImage, _ entry: [String: Any], fraction: CGFloat) {
      context.saveGraphicsState()
      context.imageInterpolation = .high
      let selected = mode ?? viewMode
      if selected == .surfaceScroll || selected == .peek {
        let scale = window?.backingScaleFactor ?? 1
        var viewport = CGSize(width: extent.width * scale, height: extent.height * scale)
        // Settings previews represent the display's crop. A tiny native crop
        // could otherwise show only a black corner of the source image.
        if isPreview, let screen = window?.screen ?? NSScreen.main {
          viewport = CGSize(
            width: screen.frame.width * screen.backingScaleFactor,
            height: screen.frame.height * screen.backingScaleFactor)
        } else {
          context.imageInterpolation = .low
        }
        let pixelSize = min(extent.width / viewport.width, extent.height / viewport.height)
        let canvas = NSRect(
          x: (extent.width - viewport.width * pixelSize) / 2,
          y: (extent.height - viewport.height * pixelSize) / 2,
          width: viewport.width * pixelSize, height: viewport.height * pixelSize)
        context.cgContext.clip(to: canvas)
        if selected == .peek {
          let center = solarPeekCenter(
            viewport: viewport, limbRadius: image.size.width * (entry["limb_uv"] as? Double ?? 0.4))
          let transform = NSAffineTransform()
          transform.translateX(
            by: canvas.minX + center.x * pixelSize, yBy: canvas.maxY - center.y * pixelSize)
          transform.rotate(byRadians: -angle)
          transform.scale(by: pixelSize)
          transform.translateX(by: -image.size.width / 2, yBy: -image.size.height / 2)
          transform.concat()
          image.draw(
            in: NSRect(origin: .zero, size: image.size), from: .zero, operation: .sourceOver,
            fraction: fraction)
        } else {
          let origin = SolarSurfacePath(image: image.size, viewport: viewport).origin(at: angle)
          image.draw(
            in: NSRect(
              x: canvas.minX - origin.x * pixelSize,
              y: canvas.maxY - (image.size.height - origin.y) * pixelSize,
              width: image.size.width * pixelSize, height: image.size.height * pixelSize),
            from: .zero, operation: .sourceOver, fraction: fraction)
        }
        context.restoreGraphicsState()
        return
      }
      let radius = max(extent.width, 1.16 * extent.height)
      let transform = NSAffineTransform()
      transform.translateX(by: extent.width / 2, yBy: extent.height * 0.52 - radius)
      transform.rotate(byRadians: -angle)
      transform.scale(by: radius / (image.size.width * (entry["limb_uv"] as? Double ?? 0.4)))
      transform.translateX(by: -image.size.width / 2, yBy: -image.size.height / 2)
      transform.concat()
      image.draw(
        in: NSRect(origin: .zero, size: image.size), from: .zero, operation: .sourceOver,
        fraction: fraction)
      context.restoreGraphicsState()
    }
    band(image, current, fraction: 1)
    let start = scene?["transition_start"] as? Double ?? 0
    let duration = max(0.001, scene?["transition_seconds"] as? Double ?? 10)
    let blend = now < start ? 1 : max(0, min(1, (now - start) / duration))
    if blend < 1, !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion,
      let previous = previousImage, let old = scene?["previous"] as? [String: Any]
    {
      band(previous, old, fraction: 1 - blend)
    }
  }
  @objc var sceneLoaded: Bool { currentImage != nil }
  @objc var sceneFault: String? { sceneError }
  @objc func captureFrame(_ path: String, atTime time: Double) {
    captureFrame(path, at: time, mode: nil)
  }
  @objc func captureFrame(_ path: String, atTime time: Double, viewMode name: String) {
    captureFrame(path, at: time, mode: SolarViewMode(rawValue: name) ?? .horizon)
  }
  private func captureFrame(_ path: String, at time: Double, mode: SolarViewMode?) {
    let scale = window?.backingScaleFactor ?? 1
    let width = Int(renderingBounds.width * scale)
    let height = Int(renderingBounds.height * scale)
    guard
      let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height, bitsPerSample: 8,
        samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
        bytesPerRow: width * 4, bitsPerPixel: 32),
      let context = NSGraphicsContext(bitmapImageRep: rep)
    else { return }
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = context
    context.cgContext.scaleBy(x: scale, y: scale)
    let captureAngle = mode.map { _ in
      Double(solarRotationAngle(at: time, frozenAngle: nil, phaseOffset: 0))
    }
    drawScene(at: time, mode: mode, angle: captureAngle)
    NSGraphicsContext.restoreGraphicsState()
    try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: path))
  }
  override var hasConfigureSheet: Bool { false }
}
