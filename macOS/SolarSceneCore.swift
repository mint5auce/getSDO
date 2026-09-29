import AppKit
import IOKit.ps
import MetalKit

func solarTime() -> Double { Double(clock_gettime_nsec_np(CLOCK_MONOTONIC_RAW)) / 1_000_000_000 }
func solarRotationAngle(at now: Double, frozenAngle: Float?, phaseOffset: Float) -> Float {
  frozenAngle
    ?? (NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
      ? 0
      : (Float(now.truncatingRemainder(dividingBy: 1200) / 1200 * 2 * .pi) + phaseOffset)
        .truncatingRemainder(dividingBy: 2 * .pi))
}
enum SolarViewMode: String, CaseIterable {
  case horizon = "solar-horizon"
  case surfaceScroll = "surface-scroll"
  case peek = "solar-peek"

  var title: String {
    switch self {
    case .horizon: return "Solar Horizon"
    case .surfaceScroll: return "Surface Scroll"
    case .peek: return "Solar Peek"
    }
  }
  init(playback: [String: Any]?) {
    self = SolarViewMode(rawValue: playback?["view_mode"] as? String ?? "") ?? .horizon
  }
}

func solarPeekCenter(viewport: CGSize, limbRadius: CGFloat) -> CGPoint {
  // Match the reference limb at 45% of the top edge and 21% of the bottom.
  // The measured source radius remains unchanged, including on Retina displays.
  let chord = hypot(viewport.width * 0.24, viewport.height)
  guard chord > 0 else { return .zero }
  let distance = sqrt(max(0, limbRadius * limbRadius - chord * chord / 4))
  return CGPoint(
    x: max(viewport.width * 0.7, viewport.width * 0.33 + viewport.height / chord * distance),
    y: viewport.height / 2 + viewport.width * 0.24 / chord * distance)
}

// A closed scan visits every part of the image, even in a small preview.
// Coordinates are source pixels, with one source pixel per backing pixel.
struct SolarSurfacePath {
  private let points: [CGPoint]
  private let lengths: [CGFloat]
  private let total: CGFloat

  init(image: CGSize, viewport: CGSize) {
    let travel = CGSize(
      width: max(0, image.width - viewport.width),
      height: max(0, image.height - viewport.height))
    let offset = CGPoint(
      x: min(0, (image.width - viewport.width) / 2),
      y: min(0, (image.height - viewport.height) / 2))
    var route = [CGPoint.zero]
    if travel.width == 0 || travel.height == 0 {
      route.append(CGPoint(x: travel.width, y: travel.height))
    } else {
      let rows = max(2, Int(ceil(travel.height / max(1, viewport.height))) + 1)
      for row in 0..<rows {
        let y = travel.height * CGFloat(row) / CGFloat(rows - 1)
        if row > 0 { route.append(CGPoint(x: row.isMultiple(of: 2) ? 0 : travel.width, y: y)) }
        route.append(CGPoint(x: row.isMultiple(of: 2) ? travel.width : 0, y: y))
      }
      if route.last!.x != 0 { route.append(CGPoint(x: 0, y: travel.height)) }
    }
    route.append(.zero)
    points = route.map { CGPoint(x: $0.x + offset.x, y: $0.y + offset.y) }
    lengths = zip(route, route.dropFirst()).map { hypot($1.x - $0.x, $1.y - $0.y) }
    total = lengths.reduce(0, +)
  }

  func origin(at angle: Double) -> CGPoint {
    guard total > 0 else { return points[0] }
    let turn = angle / (2 * Double.pi)
    var distance = CGFloat(turn - floor(turn)) * total
    for (index, length) in lengths.enumerated() where length > 0 {
      if distance <= length {
        let t = distance / length
        // Zero velocity and acceleration at turns and the loop boundary.
        let eased = t * t * t * (10 + t * (-15 + 6 * t))
        let a = points[index]
        let b = points[index + 1]
        return CGPoint(x: a.x + (b.x - a.x) * eased, y: a.y + (b.y - a.y) * eased)
      }
      distance -= length
    }
    return points[0]
  }
}

func solarToggledPlayback(_ value: [String: Any], at now: Double) -> [String: Any] {
  var playback = value
  let phase = now.truncatingRemainder(dividingBy: 1200) / 1200 * 2 * Double.pi
  if let paused = playback.removeValue(forKey: "paused_angle") as? Double {
    playback["phase_offset"] = paused - phase
  } else {
    playback["paused_angle"] = phase + (playback["phase_offset"] as? Double ?? 0)
  }
  return playback
}
// Use the account home even when hosted by the legacy screensaver container.
let solarHome = URL(fileURLWithPath: String(cString: getpwuid(getuid()).pointee.pw_dir))
let solarSupport = solarHome.appendingPathComponent("Library/Application Support/getSDO")
func readJSON(_ name: String, root: URL = solarSupport) -> [String: Any]? {
  guard let data = try? Data(contentsOf: root.appendingPathComponent(name)) else { return nil }
  return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
}
func writeJSON(_ name: String, _ value: [String: Any]) {
  if let data = try? JSONSerialization.data(
    withJSONObject: value, options: [.prettyPrinted, .sortedKeys])
  {
    try? data.write(to: solarSupport.appendingPathComponent(name), options: .atomic)
  }
}

private let shader = """
  #include <metal_stdlib>
  using namespace metal;
  struct Vertex { float4 position [[position]]; float2 uv; };
  struct Params {
      float angle; float aspect; float limb; float oldLimb; float blend; float apex;
      float surface; float originX; float originY; float oldOriginX; float oldOriginY;
      float centerX; float centerY; float oldCenterX; float oldCenterY;
  };
  vertex Vertex solarVertex(uint id [[vertex_id]]) {
      float2 p[] = {float2(-1,-1),float2(3,-1),float2(-1,3)};
      Vertex v; v.position=float4(p[id],0,1); v.uv=float2((p[id].x+1)*.5,(1-p[id].y)*.5); return v;
  }
  fragment float4 solarFragment(Vertex v [[stage_in]], constant Params &p [[buffer(0)]],
   texture2d<float> image [[texture(0)]], texture2d<float> previous [[texture(1)]]) {
      constexpr sampler s(filter::linear, address::clamp_to_zero);
      if (p.surface > 1.5) {
          float c=cos(p.angle), t=sin(p.angle);
          float2 d=v.position.xy-float2(p.centerX,p.centerY);
          float2 oldD=v.position.xy-float2(p.oldCenterX,p.oldCenterY);
          float2 q=float2(d.x*c+d.y*t,-d.x*t+d.y*c);
          float2 oldQ=float2(oldD.x*c+oldD.y*t,-oldD.x*t+oldD.y*c);
          float2 uv=.5+q/float2(image.get_width(),image.get_height());
          float2 oldUV=.5+oldQ/float2(previous.get_width(),previous.get_height());
          return float4(mix(previous.sample(s,oldUV).rgb,image.sample(s,uv).rgb,p.blend),1);
      }
      if (p.surface > .5) {
          float2 uv=(v.position.xy+float2(p.originX,p.originY)) / float2(image.get_width(),image.get_height());
          float2 oldUV=(v.position.xy+float2(p.oldOriginX,p.oldOriginY)) / float2(previous.get_width(),previous.get_height());
          return float4(mix(previous.sample(s,oldUV).rgb,image.sample(s,uv).rgb,p.blend),1);
      }
      float radius=max(1.0,1.16/p.aspect);
      float2 d=float2(v.uv.x-.5, v.uv.y/p.aspect-(p.apex/p.aspect+radius))/radius;
      float c=cos(p.angle), t=sin(p.angle);
      float2 q=float2(d.x*c+d.y*t,-d.x*t+d.y*c);
      float3 now=image.sample(s,0.5+q*p.limb).rgb;
      float3 old=previous.sample(s,0.5+q*p.oldLimb).rgb;
      return float4(mix(old,now,p.blend),1);
  }
  """
struct SolarParams {
  var angle: Float = 0
  var aspect: Float = 1
  var limb: Float = 0.4
  var oldLimb: Float = 0.4
  var blend: Float = 1
  var apex: Float = 0.48
  var surface: Float = 0
  var originX: Float = 0
  var originY: Float = 0
  var oldOriginX: Float = 0
  var oldOriginY: Float = 0
  var centerX: Float = 0
  var centerY: Float = 0
  var oldCenterX: Float = 0
  var oldCenterY: Float = 0
}

final class SolarRenderer: NSObject, MTKViewDelegate {
  let support: URL
  let device: MTLDevice
  let queue: MTLCommandQueue
  let pipeline: MTLRenderPipelineState
  var texture: MTLTexture?
  var previous: MTLTexture?
  var scene: [String: Any]?
  var sceneID = ""
  var nextCheck = 0.0
  var fault: String?
  var frozenAngle: Float?
  var phaseOffset: Float = 0
  var viewMode: SolarViewMode = .horizon
  var offscreen = false
  weak var view: MTKView?
  init(view: MTKView, support: URL = solarSupport) throws {
    self.support = support
    guard let device = MTLCreateSystemDefaultDevice(), let queue = device.makeCommandQueue() else {
      throw NSError(
        domain: "SolarHorizon", code: 1, userInfo: [NSLocalizedDescriptionKey: "Metal unavailable"])
    }
    self.device = device
    self.queue = queue
    self.view = view
    let library = try device.makeLibrary(source: shader, options: nil)
    let descriptor = MTLRenderPipelineDescriptor()
    descriptor.vertexFunction = library.makeFunction(name: "solarVertex")
    descriptor.fragmentFunction = library.makeFunction(name: "solarFragment")
    descriptor.colorAttachments[0].pixelFormat = .bgra8Unorm_srgb
    pipeline = try device.makeRenderPipelineState(descriptor: descriptor)
    super.init()
    view.device = device
    view.colorPixelFormat = .bgra8Unorm_srgb
    view.clearColor = MTLClearColorMake(0, 0, 0, 1)
    view.framebufferOnly = true
    view.delegate = self
    reload()
  }
  func load(_ entry: [String: Any]?) throws -> MTLTexture? {
    guard let path = entry?["texture"] as? String else { return nil }
    let url = URL(fileURLWithPath: path).standardizedFileURL.resolvingSymlinksInPath()
    let allowed =
      support.appendingPathComponent("scenes").standardizedFileURL.resolvingSymlinksInPath().path
      + "/"
    guard url.path.hasPrefix(allowed) else { throw NSError(domain: "SolarHorizon", code: 2) }
    return try MTKTextureLoader(device: device).newTexture(
      URL: url, options: [.SRGB: true, .textureUsage: MTLTextureUsage.shaderRead.rawValue])
  }
  func reload() {
    let now = solarTime()
    defer { nextCheck = now + 2 }
    let playback = readJSON("playback.json", root: support)
    viewMode = SolarViewMode(playback: playback)
    phaseOffset = Float(playback?["phase_offset"] as? Double ?? 0)
    frozenAngle = (playback?["paused_angle"] as? Double).map { Float($0) }
    guard let candidate = readJSON("scene.json", root: support),
      let current = candidate["current"] as? [String: Any], let id = current["id"] as? String
    else {
      if fault == nil {
        fault = "Prepared scene is missing or unreadable at \(support.path)"
        NSLog("Solar Horizon: %@", fault!)
      }
      return
    }
    guard id != sceneID else { return }
    do {
      let next = try load(current)
      let old = try load(candidate["previous"] as? [String: Any])
      texture = next
      previous = old ?? next
      scene = candidate
      sceneID = id
      fault = nil
      NSLog("Solar Horizon: loaded scene %@", id)
    } catch {
      fault = "Scene could not be loaded: \(error.localizedDescription)"
      NSLog("Solar Horizon: %@", fault!)
      if texture == nil, let old = candidate["previous"] as? [String: Any],
        let fallback = try? load(old)
      {
        texture = fallback
        previous = fallback
        scene = ["current": old, "transition_start": 0, "transition_seconds": 10]
      }
    }
  }
  func mtkView(_ view: MTKView, drawableSizeWillChange size: CGSize) {}
  func rotationAngle(at now: Double) -> Float {
    solarRotationAngle(at: now, frozenAngle: frozenAngle, phaseOffset: phaseOffset)
  }
  func draw(in view: MTKView) { render(in: view) }
  func render(in view: MTKView, at time: Double? = nil, capture: URL? = nil) {
    let now = time ?? solarTime()
    if now >= nextCheck { reload() }
    guard !offscreen, let drawable = view.currentDrawable,
      let descriptor = view.currentRenderPassDescriptor,
      let command = queue.makeCommandBuffer(),
      let encoder = command.makeRenderCommandEncoder(descriptor: descriptor)
    else { return }
    if let texture = texture, let previous = previous,
      let current = scene?["current"] as? [String: Any]
    {
      let old = scene?["previous"] as? [String: Any]
      let reduced = NSWorkspace.shared.accessibilityDisplayShouldReduceMotion
      let angle = rotationAngle(at: now)
      let start = scene?["transition_start"] as? Double ?? 0
      let duration = scene?["transition_seconds"] as? Double ?? 10
      let blend: Float =
        now < start ? 1 : Float(max(0, min(1, (now - start) / max(0.001, duration))))
      var params = SolarParams(
        angle: angle, aspect: Float(view.drawableSize.width / max(1, view.drawableSize.height)),
        limb: Float(current["limb_uv"] as? Double ?? 0.4),
        oldLimb: Float(old?["limb_uv"] as? Double ?? current["limb_uv"] as? Double ?? 0.4),
        blend: reduced ? 1 : blend, apex: 0.48)
      if viewMode == .surfaceScroll {
        let origin = SolarSurfacePath(
          image: CGSize(width: texture.width, height: texture.height), viewport: view.drawableSize
        ).origin(at: Double(angle))
        let oldOrigin = SolarSurfacePath(
          image: CGSize(width: previous.width, height: previous.height), viewport: view.drawableSize
        ).origin(at: Double(angle))
        params.surface = 1
        params.originX = Float(origin.x)
        params.originY = Float(origin.y)
        params.oldOriginX = Float(oldOrigin.x)
        params.oldOriginY = Float(oldOrigin.y)
      } else if viewMode == .peek {
        let center = solarPeekCenter(
          viewport: view.drawableSize, limbRadius: CGFloat(texture.width) * CGFloat(params.limb))
        let oldCenter = solarPeekCenter(
          viewport: view.drawableSize, limbRadius: CGFloat(previous.width) * CGFloat(params.oldLimb)
        )
        params.surface = 2
        params.centerX = Float(center.x)
        params.centerY = Float(center.y)
        params.oldCenterX = Float(oldCenter.x)
        params.oldCenterY = Float(oldCenter.y)
      }
      encoder.setRenderPipelineState(pipeline)
      encoder.setFragmentBytes(&params, length: MemoryLayout<SolarParams>.stride, index: 0)
      encoder.setFragmentTexture(texture, index: 0)
      encoder.setFragmentTexture(previous, index: 1)
      encoder.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
    }
    encoder.endEncoding()
    var output: MTLBuffer?
    if capture != nil {
      let width = drawable.texture.width
      let height = drawable.texture.height
      output = device.makeBuffer(length: width * height * 4, options: .storageModeShared)
      if let buffer = output, let blit = command.makeBlitCommandEncoder() {
        blit.copy(
          from: drawable.texture, sourceSlice: 0, sourceLevel: 0,
          sourceOrigin: MTLOrigin(x: 0, y: 0, z: 0),
          sourceSize: MTLSize(width: width, height: height, depth: 1), to: buffer,
          destinationOffset: 0, destinationBytesPerRow: width * 4,
          destinationBytesPerImage: width * height * 4)
        blit.endEncoding()
      }
    }
    command.present(drawable)
    command.commit()
    if let target = capture, let buffer = output {
      command.waitUntilCompleted()
      let width = drawable.texture.width
      let height = drawable.texture.height
      let bytes = buffer.contents().bindMemory(to: UInt8.self, capacity: width * height * 4)
      let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: width, pixelsHigh: height, bitsPerSample: 8,
        samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
        bytesPerRow: width * 4, bitsPerPixel: 32)!
      for pixel in 0..<width * height {
        rep.bitmapData![pixel * 4] = bytes[pixel * 4 + 2]
        rep.bitmapData![pixel * 4 + 1] = bytes[pixel * 4 + 1]
        rep.bitmapData![pixel * 4 + 2] = bytes[pixel * 4]
        rep.bitmapData![pixel * 4 + 3] = 255
      }
      try? rep.representation(using: .png, properties: [:])?.write(to: target)
    }
  }
  func updatePower(checkOcclusion: Bool = true) {
    guard let info = IOPSCopyPowerSourcesInfo()?.takeRetainedValue() else { return }
    let battery =
      IOPSGetProvidingPowerSourceType(info)?.takeUnretainedValue() as String?
      == kIOPSBatteryPowerValue
    view?.preferredFramesPerSecond =
      NSWorkspace.shared.accessibilityDisplayShouldReduceMotion || frozenAngle != nil
      ? 1 : (battery ? 30 : 60)
    view?.isPaused =
      offscreen || (checkOcclusion && !(view?.window?.occlusionState.contains(.visible) ?? true))
  }
}
