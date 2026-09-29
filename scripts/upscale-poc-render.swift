// Review-only offscreen harness, compiled alongside the unmodified production core.
import AppKit
import ImageIO
import MetalKit
import UniformTypeIdentifiers

@main struct PoCRender {
  static func main() throws {
    _ = NSApplication.shared
    guard let screen = NSScreen.main else { fatalError("No connected main display") }
    let backing = screen.convertRectToBacking(screen.frame)
    let display: [String: Any] = [
      "width": Int(backing.width), "height": Int(backing.height),
      "logical_width": Int(screen.frame.width), "logical_height": Int(screen.frame.height),
      "backing_scale": screen.backingScaleFactor,
      "os": ProcessInfo.processInfo.operatingSystemVersionString,
      "gpu": MTLCreateSystemDefaultDevice()?.name ?? "unknown",
      "physical_memory_bytes": ProcessInfo.processInfo.physicalMemory,
    ]
    if CommandLine.arguments[1] == "display" {
      print(String(data: try JSONSerialization.data(withJSONObject: display), encoding: .utf8)!)
      return
    }
    let folder = URL(fileURLWithPath: CommandLine.arguments[1])
    let config =
      try JSONSerialization.jsonObject(
        with: Data(contentsOf: folder.appendingPathComponent("render-jobs.json"))) as! [String: Any]
    let width = config["width"] as! Int
    let height = config["height"] as! Int
    let limb = Float(config["limb_uv"] as! Double)
    let view = MTKView(frame: .zero)
    let renderer = try SolarRenderer(view: view, support: folder)
    view.isPaused = true
    let targetDescriptor = MTLTextureDescriptor.texture2DDescriptor(
      pixelFormat: .bgra8Unorm_srgb, width: width, height: height, mipmapped: false)
    targetDescriptor.usage = [.renderTarget]
    targetDescriptor.storageMode = .private
    let target = renderer.device.makeTexture(descriptor: targetDescriptor)!
    let buffer = renderer.device.makeBuffer(
      length: width * height * 4, options: .storageModeShared)!
    var loadedVariant = ""
    var texture: MTLTexture?
    var allocations: [String: Any] = [:]
    var measurements: [[String: Any]] = []

    func frame(at seconds: Double) throws {
      let descriptor = MTLRenderPassDescriptor()
      descriptor.colorAttachments[0].texture = target
      descriptor.colorAttachments[0].loadAction = .clear
      descriptor.colorAttachments[0].storeAction = .store
      descriptor.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 0, 1)
      let command = renderer.queue.makeCommandBuffer()!
      let encoder = command.makeRenderCommandEncoder(descriptor: descriptor)!
      let angle = Float(seconds.truncatingRemainder(dividingBy: 1200) / 1200 * 2 * .pi)
      var params = SolarParams(
        angle: solarRotationAngle(at: seconds, frozenAngle: angle, phaseOffset: 0),
        aspect: Float(width) / Float(height), limb: limb, oldLimb: limb, blend: 1, apex: 0.48)
      encoder.setRenderPipelineState(renderer.pipeline)
      encoder.setFragmentBytes(&params, length: MemoryLayout<SolarParams>.stride, index: 0)
      encoder.setFragmentTexture(texture, index: 0)
      encoder.setFragmentTexture(texture, index: 1)
      encoder.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
      encoder.endEncoding()
      let blit = command.makeBlitCommandEncoder()!
      blit.copy(
        from: target, sourceSlice: 0, sourceLevel: 0, sourceOrigin: MTLOrigin(x: 0, y: 0, z: 0),
        sourceSize: MTLSize(width: width, height: height, depth: 1), to: buffer,
        destinationOffset: 0, destinationBytesPerRow: width * 4,
        destinationBytesPerImage: width * height * 4)
      blit.endEncoding()
      command.commit()
      command.waitUntilCompleted()
      if command.status == .error { throw command.error! }
    }

    func savePNG(_ output: URL) throws {
      let data = Data(bytes: buffer.contents(), count: width * height * 4)
      let provider = CGDataProvider(data: data as CFData)!
      let info = CGBitmapInfo.byteOrder32Little.union(
        CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipFirst.rawValue))
      let image = CGImage(
        width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32,
        bytesPerRow: width * 4, space: CGColorSpace(name: CGColorSpace.sRGB)!,
        bitmapInfo: info, provider: provider, decode: nil,
        shouldInterpolate: false, intent: .defaultIntent)!
      let destination = CGImageDestinationCreateWithURL(
        output as CFURL, UTType.png.identifier as CFString, 1, nil)!
      CGImageDestinationAddImage(destination, image, nil)
      guard CGImageDestinationFinalize(destination) else { fatalError("PNG publication failed") }
    }

    for job in config["jobs"] as! [[String: Any]] {
      let variant = job["variant"] as! String
      if variant != loadedVariant {
        texture = nil
        texture = try renderer.load([
          "texture": folder.appendingPathComponent("scenes/\(variant)/texture.png").path
        ])
        guard let image = texture else { fatalError("Texture unavailable") }
        allocations[variant] = [
          "width": image.width, "height": image.height, "allocated_bytes": image.allocatedSize,
          "pixel_format": image.pixelFormat.rawValue, "mipmap_levels": image.mipmapLevelCount,
          "two_distinct_textures_bytes": image.allocatedSize * 2,
        ]
        loadedVariant = variant
      }
      let seconds = job["seconds"] as! Double
      let output = folder.appendingPathComponent(job["output"] as! String)
      let started = ProcessInfo.processInfo.systemUptime
      if let duration = job["duration"] as? Double {
        let fps = job["fps"] as! Int
        let speed = job["speed"] as! Double
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = [
          "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo",
          "-pixel_format", "bgra", "-video_size", "\(width)x\(height)", "-framerate", "\(fps)",
          "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "14",
          "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "iec61966-2-1",
          "-colorspace", "bt709", "-movflags", "+faststart", output.path,
        ]
        let pipe = Pipe()
        process.standardInput = pipe
        try process.run()
        for index in 0..<Int(duration * Double(fps)) {
          try autoreleasepool {
            try frame(at: seconds + Double(index) / Double(fps) * speed)
            try pipe.fileHandleForWriting.write(
              contentsOf: Data(
                bytesNoCopy: buffer.contents(), count: width * height * 4, deallocator: .none))
          }
        }
        try pipe.fileHandleForWriting.close()
        process.waitUntilExit()
        guard process.terminationStatus == 0 else { fatalError("Video encoding failed") }
      } else {
        try frame(at: seconds)
        try savePNG(output)
      }
      measurements.append([
        "output": job["output"]!, "elapsed_seconds": ProcessInfo.processInfo.systemUptime - started,
      ])
      print("Rendered \(job["output"]!)")
      fflush(stdout)
    }
    try JSONSerialization.data(
      withJSONObject: ["textures": allocations, "render_jobs": measurements],
      options: [.prettyPrinted, .sortedKeys]
    )
    .write(to: folder.appendingPathComponent("metal-measurements.json"))
  }
}
