//@ pragma UseQApplication
import Quickshell
import "notifications"

ShellRoot {
    // Une barre par écran, y compris si les sorties changent pendant la session.
    // CONTRACT: un seul serveur D-Bus pour toutes les sorties.
    NotificationService { id: rootNotificationService }

    Variants {
        model: Quickshell.screens

        Bar { notificationService: rootNotificationService }
    }
}
