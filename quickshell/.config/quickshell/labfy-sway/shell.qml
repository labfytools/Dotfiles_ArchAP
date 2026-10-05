//@ pragma UseQApplication
import Quickshell
import Quickshell.Io
import "notifications"
import "theme"

ShellRoot {
    // CONTRACT: seul ce point d'entrée reçoit les changements live du backend.
    // Aucun état de thème n'est écrit par Theme.qml.
    IpcHandler {
        target: "appearance"
        function setTheme(flavor: string, accent: string): bool {
            return AppearanceController.applyTheme(flavor, accent);
        }
        function currentTheme(): string {
            return AppearanceController.effectiveFlavor + "/" + AppearanceController.effectiveAccent;
        }
        function effectiveState(): string {
            return AppearanceController.effectiveState();
        }
        function publishState(payload: string): bool {
            return AppearanceController.acceptPublished(payload);
        }
        function publishNightLight(payload: string): bool {
            return AppearanceController.acceptPublishedNightLight(payload);
        }
    }
    // Une barre par écran, y compris si les sorties changent pendant la session.
    // CONTRACT: un seul serveur D-Bus pour toutes les sorties.
    NotificationService { id: rootNotificationService }

    Variants {
        model: Quickshell.screens

        Bar { notificationService: rootNotificationService }
    }
}
