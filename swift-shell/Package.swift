// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "JarvisShell",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .library(name: "JarvisClient", targets: ["JarvisClient"]),
        .executable(name: "jarvis-host-probe", targets: ["JarvisHostProbe"]),
        .executable(name: "jarvis-menu-bar", targets: ["JarvisMenuBar"]),
        .executable(name: "jarvis-status-helper", targets: ["JarvisStatusHelper"])
    ],
    targets: [
        .target(name: "JarvisClient"),
        .executableTarget(
            name: "JarvisHostProbe",
            dependencies: ["JarvisClient"]
        ),
        .executableTarget(
            name: "JarvisMenuBar",
            dependencies: ["JarvisClient"]
        ),
        .executableTarget(
            name: "JarvisStatusHelper",
            dependencies: ["JarvisClient"]
        )
    ]
)
