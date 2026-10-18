import SwiftUI

@main
struct EduPilotApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}

struct RootView: View {
    @State private var isOnline = true

    var body: some View {
        NavigationStack {
            EduPilotWebView(isOnline: $isOnline)
                .overlay {
                    if !isOnline {
                        ContentUnavailableView("Connexion indisponible",
                                               systemImage: "wifi.slash",
                                               description: Text("Vérifiez votre connexion Internet puis réessayez."))
                            .background(.regularMaterial)
                    }
                }
                .navigationTitle("EduPilot")
                .navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .topBarTrailing) {
                        ShareLink(item: URL(string: "https://edupilot.ci")!) {
                            Image(systemName: "square.and.arrow.up")
                        }
                    }
                }
        }
    }
}
