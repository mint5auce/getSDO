import AppKit
import MetalKit

final class SolarApp: NSObject, NSApplicationDelegate {
  var windows: [NSWindow] = []
  var renderers: [SolarRenderer] = []
  var status: NSStatusItem!
  var timer: Timer?
  var refreshing = false
  var sourceItem = NSMenuItem(title: "Waiting for a prepared scene", action: nil, keyEquivalent: "")
  var previewWindows: [NSWindow] = []
  var viewItems: [NSMenuItem] = []
  func applicationDidFinishLaunching(_ notification: Notification) {
    let running = ["uk.jonh.solar-horizon.app", "uk.jonh.getSDO.app"].flatMap {
      NSRunningApplication.runningApplications(withBundleIdentifier: $0)
    }
    if running
      .contains(where: { $0.processIdentifier != ProcessInfo.processInfo.processIdentifier })
    {
      NSApp.terminate(nil)
      return
    }
    NSApp.setActivationPolicy(.accessory)
    status = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    let icon = NSImage(systemSymbolName: "sun.haze", accessibilityDescription: "Solar Horizon")?
      .withSymbolConfiguration(.init(pointSize: 16, weight: .regular))
    icon?.isTemplate = true
    status.button?.image = icon
    status.button?.toolTip = "Solar Horizon · SDO/AIA 193 Å"
    status.button?.setAccessibilityLabel("Solar Horizon")
    let menu = NSMenu()
    menu.addItem(withTitle: "Solar Horizon · SDO/AIA 193 Å", action: nil, keyEquivalent: "")
    menu.addItem(sourceItem)
    menu.addItem(.separator())
    addViewChoices(to: menu)
    menu.addItem(.separator())
    for (title, action) in [
      ("Preview", #selector(preview)), ("Pause / resume", #selector(pause)),
      ("Refresh now", #selector(refreshNow)), ("Open originals", #selector(openOriginals)),
      ("Quit", #selector(quit)),
    ] {
      let item = menu.addItem(withTitle: title, action: action, keyEquivalent: "")
      item.target = self
    }
    status.menu = menu
    let mainMenu = NSMenu()
    let applicationMenu = NSMenuItem(title: "Solar Horizon", action: nil, keyEquivalent: "")
    applicationMenu.submenu = NSMenu()
    addViewChoices(to: applicationMenu.submenu!)
    applicationMenu.submenu!.addItem(.separator())
    for (title, action, key) in [
      ("Preview", #selector(preview), "p"), ("Pause / resume", #selector(pause), ""),
      ("Quit Solar Horizon", #selector(quit), "q"),
    ] {
      let item = applicationMenu.submenu!.addItem(
        withTitle: title, action: action, keyEquivalent: key)
      item.target = self
    }
    mainMenu.addItem(applicationMenu)
    NSApp.mainMenu = mainMenu
    updateViewChoices()
    buildDesktops()
    NotificationCenter.default.addObserver(
      self, selector: #selector(buildDesktops),
      name: NSApplication.didChangeScreenParametersNotification, object: nil)
    NotificationCenter.default.addObserver(
      self, selector: #selector(powerChanged), name: NSWindow.didChangeOcclusionStateNotification,
      object: nil)
    NotificationCenter.default.addObserver(
      self, selector: #selector(previewClosed(_:)), name: NSWindow.willCloseNotification,
      object: nil)
    let workspace = NSWorkspace.shared.notificationCenter
    workspace.addObserver(
      self, selector: #selector(powerChanged),
      name: NSWorkspace.accessibilityDisplayOptionsDidChangeNotification, object: nil)
    for name in [NSWorkspace.willSleepNotification, NSWorkspace.screensDidSleepNotification] {
      workspace.addObserver(self, selector: #selector(suspend), name: name, object: nil)
    }
    for name in [NSWorkspace.didWakeNotification, NSWorkspace.screensDidWakeNotification] {
      workspace.addObserver(self, selector: #selector(resume), name: name, object: nil)
    }
    timer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
      self?.tick()
    }
    tick()
    if CommandLine.arguments.contains("--preview") { preview() }
  }
  func addViewChoices(to menu: NSMenu) {
    for mode in SolarViewMode.allCases {
      let item = menu.addItem(
        withTitle: mode.title, action: #selector(selectView(_:)), keyEquivalent: "")
      item.target = self
      item.representedObject = mode.rawValue
      viewItems.append(item)
    }
  }
  func updateViewChoices() {
    let mode = SolarViewMode(playback: readJSON("playback.json"))
    for item in viewItems {
      item.state = item.representedObject as? String == mode.rawValue ? .on : .off
    }
    for window in previewWindows { window.title = "\(mode.title) preview" }
  }
  @objc func selectView(_ sender: NSMenuItem) {
    guard let raw = sender.representedObject as? String, let mode = SolarViewMode(rawValue: raw)
    else { return }
    var playback = readJSON("playback.json") ?? [:]
    playback["view_mode"] = mode.rawValue
    writeJSON("playback.json", playback)
    for renderer in renderers {
      renderer.reload()
      renderer.view?.draw()
    }
    updateViewChoices()
  }
  func makeView(_ frame: NSRect) -> MTKView {
    let view = MTKView(frame: frame)
    do {
      let renderer = try SolarRenderer(view: view)
      renderers.append(renderer)
      renderer.updatePower()
    } catch { NSLog("Solar Horizon: %@", error.localizedDescription) }
    return view
  }
  @objc func buildDesktops() {
    for window in windows { window.close() }
    renderers.removeAll { renderer in
      renderer.view?.window == nil || windows.contains { $0 === renderer.view?.window }
    }
    windows.removeAll()
    for screen in NSScreen.screens {
      let window = NSWindow(
        contentRect: screen.frame, styleMask: .borderless, backing: .buffered, defer: false,
        screen: screen)
      window.isReleasedWhenClosed = false
      window.backgroundColor = .black
      window.level = NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.desktopWindow)))
      window.ignoresMouseEvents = true
      window.collectionBehavior = [.canJoinAllSpaces, .stationary, .ignoresCycle]
      window.contentView = makeView(NSRect(origin: .zero, size: screen.frame.size))
      window.orderBack(nil)
      windows.append(window)
    }
  }
  @objc func preview() {
    let window = NSWindow(
      contentRect: NSRect(x: 0, y: 0, width: 1000, height: 650),
      styleMask: [.titled, .closable, .resizable], backing: .buffered, defer: false)
    window.isReleasedWhenClosed = false
    window.title = "\(SolarViewMode(playback: readJSON("playback.json")).title) preview"
    window.contentView = makeView(NSRect(x: 0, y: 0, width: 1000, height: 650))
    window.center()
    window.makeKeyAndOrderFront(nil)
    previewWindows.append(window)
    NSApp.activate(ignoringOtherApps: true)
  }
  @objc func pause() {
    writeJSON(
      "playback.json", solarToggledPlayback(readJSON("playback.json") ?? [:], at: solarTime()))
    for renderer in renderers {
      renderer.reload()
      renderer.updatePower()
    }
  }
  @objc func previewClosed(_ notification: Notification) {
    guard let window = notification.object as? NSWindow,
      previewWindows.contains(where: { $0 === window })
    else { return }
    renderers.removeAll { $0.view?.window === window }
    previewWindows.removeAll { $0 === window }
  }
  @objc func refreshNow() { launchRefresh(force: true) }
  @objc func openOriginals() {
    let path =
      readJSON("config.json")?["originals"] as? String
      ?? solarHome.appendingPathComponent("Pictures/sdo-feed").path
    NSWorkspace.shared.open(URL(fileURLWithPath: path))
  }
  @objc func quit() { NSApp.terminate(nil) }
  @objc func powerChanged() { for renderer in renderers { renderer.updatePower() } }
  @objc func suspend() {
    for renderer in renderers {
      renderer.offscreen = true
      renderer.updatePower()
    }
  }
  @objc func resume() {
    for renderer in renderers {
      renderer.offscreen = false
      renderer.updatePower()
    }
    tick()
  }
  func tick() {
    for renderer in renderers { renderer.updatePower() }
    let state = readJSON("refresh-state.json")
    sourceItem.title =
      "\(state?["observation"] as? String ?? "No observation") · \(renderers.compactMap { $0.fault }.first ?? state?["status"] as? String ?? "Not refreshed")"
    launchRefresh(force: false)
  }
  func launchRefresh(force: Bool) {
    guard !refreshing, let config = readJSON("config.json"),
      let interpreter = config["python"] as? String,
      let script = config["refresh_script"] as? String
    else { return }
    refreshing = true
    let process = Process()
    process.executableURL = URL(fileURLWithPath: interpreter)
    process.arguments = [script] + (force ? ["--force"] : [])
    process.standardOutput = FileHandle.nullDevice
    process.standardError = FileHandle.nullDevice
    process.terminationHandler = { [weak self] _ in
      DispatchQueue.main.async { self?.refreshing = false }
    }
    do { try process.run() } catch {
      refreshing = false
      NSLog("Refresh: %@", error.localizedDescription)
    }
  }
}
@main
struct SolarMain {
  static func main() {
    let app = NSApplication.shared
    let delegate = SolarApp()
    app.delegate = delegate
    app.run()
  }
}
