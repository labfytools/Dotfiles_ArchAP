//@ pragma UseQApplication
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.Polkit
import "polkit"

ShellRoot {
    id: root
    property var shownFlow: fakeFlow
    QtObject { id: account1; property string displayName: "Compte de test"; property string string: "test"
        property int id: 1000; property bool isGroup: false }
    QtObject { id: account2; property string displayName: "Autre compte"; property string string: "other"
        property int id: 1001; property bool isGroup: false }
    QtObject {
        id: fakeFlow
        property string message: "Autoriser une opération de démonstration sans données personnelles ?"
        property string iconName: ""
        property string actionId: "org.example.demo"
        property var identities: [account1]
        property var selectedIdentity: account1
        property bool isResponseRequired: true
        property string inputPrompt: "Réponse de démonstration :"
        property bool responseVisible: false
        property string supplementaryMessage: ""
        property bool supplementaryIsError: false
        property bool isCompleted: false
        property bool isCancelled: false
        property bool failed: false
        property int submissions: 0
        signal authenticationFailed()
        function submit(value) { submissions++; isResponseRequired = false; }
        function cancelAuthenticationRequest() { isCancelled = true; }
    }
    QtObject {
        id: secondFlow
        property string message: "Deuxième demande de test"
        property string iconName: ""
        property string actionId: "org.example.second"
        property var identities: [account1]
        property var selectedIdentity: account1
        property bool isResponseRequired: true
        property string inputPrompt: "Réponse visible de test :"
        property bool responseVisible: true
        property string supplementaryMessage: ""
        property bool supplementaryIsError: false
        property bool isCompleted: false
        property bool isCancelled: false
        property bool failed: false
        property int submissions: 0
        signal authenticationFailed()
        function submit(value) { submissions++; isResponseRequired = false; }
        function cancelAuthenticationRequest() { isCancelled = true; }
    }
    IpcHandler {
        target: "polkitFixture"
        function state(): string {
            return JSON.stringify({waiting: fakeFlow.isResponseRequired, cancelled: fakeFlow.isCancelled,
                submissions: fakeFlow.submissions, screen: Quickshell.screens.length,
                canSubmit: dialogLoader.item ? dialogLoader.item.card.canSubmit : false});
        }
        function scenario(name: string): bool {
            if (name === "long") fakeFlow.message = "Cette opération de démonstration comporte un message volontairement long afin de contrôler le retour à la ligne et la hauteur du dialogue sur un écran compact. Aucune autorisation réelle ne sera demandée.";
            else if (name === "multi") fakeFlow.identities = [account1, account2];
            else if (name === "identitySamePrompt") {
                fakeFlow.identities = [account1, account2];
                dialogLoader.item.card.selectIdentity(account2);
            }
            else if (name === "visible") fakeFlow.responseVisible = true;
            else if (name === "error") { fakeFlow.supplementaryMessage = "Échec de test"; fakeFlow.supplementaryIsError = true; fakeFlow.failed = true; fakeFlow.authenticationFailed(); fakeFlow.isResponseRequired = true; }
            else if (name === "next") { fakeFlow.isResponseRequired = false; fakeFlow.isResponseRequired = true; }
            else if (name === "cancel") fakeFlow.cancelAuthenticationRequest();
            else if (name === "reset") {
                root.shownFlow = fakeFlow;
                fakeFlow.message = "Autoriser une opération de démonstration sans données personnelles ?";
                fakeFlow.identities = [account1]; fakeFlow.selectedIdentity = account1;
                fakeFlow.inputPrompt = "Réponse de démonstration :";
                fakeFlow.responseVisible = false; fakeFlow.supplementaryMessage = "";
                fakeFlow.isCancelled = false; fakeFlow.isCompleted = false; fakeFlow.failed = false;
                fakeFlow.isResponseRequired = true; fakeFlow.submissions = 0;
                if (dialogLoader.item) dialogLoader.item.card.clearResponse();
            }
            else return false;
            return true;
        }
        function checks(): string {
            const card = dialogLoader.item.card;
            function findField(item) {
                if (item.objectName === "polkitResponse") return item;
                for (const child of item.children || []) {
                    const found = findField(child);
                    if (found) return found;
                }
                return null;
            }
            const field = findField(card);
            if (!field) return JSON.stringify({error: "champ absent"});
            fakeFlow.isCancelled = false; fakeFlow.isCompleted = false;
            fakeFlow.isResponseRequired = true; card.busy = false;
            secondFlow.submissions = 0;
            field.clear();
            const emptySecretBlocked = card.canEdit && !card.canSubmit
                && !card.submitResponse() && fakeFlow.submissions === 0;
            field.text = "réponse fictive";
            const first = card.submitResponse();
            const second = card.submitResponse();
            const oneSubmit = first && !second && fakeFlow.submissions === 1 && field.text === "";
            fakeFlow.supplementaryMessage = "Échec de test";
            fakeFlow.supplementaryIsError = true;
            fakeFlow.authenticationFailed(); fakeFlow.isResponseRequired = true;
            const retry = card.canEdit && !card.canSubmit && field.text === "";
            field.text = "ancienne réponse";
            fakeFlow.inputPrompt = "Nouvelle question :";
            const successive = field.text === "";
            fakeFlow.identities = [account1, account2];
            fakeFlow.isResponseRequired = true; card.busy = false;
            field.text = "à effacer au changement de compte";
            card.selectIdentity(account2);
            fakeFlow.inputPrompt = "Nouvelle identité :";
            const identity = fakeFlow.selectedIdentity === account2 && field.text === ""
                && card.canEdit && !card.canSubmit;
            root.shownFlow = null;
            const disappeared = field.text === "" && !card.canSubmit;
            root.shownFlow = secondFlow;
            secondFlow.isCancelled = false; secondFlow.isResponseRequired = true;
            field.text = "réponse fictive 2";
            const nextFlow = card.submitResponse() && secondFlow.submissions === 1
                && fakeFlow.submissions === 1 && field.text === "";
            root.shownFlow = fakeFlow;
            fakeFlow.isCancelled = false; fakeFlow.isResponseRequired = true; card.busy = false;
            field.text = "à effacer";
            card.cancelRequest();
            const cancelled = fakeFlow.isCancelled && field.text === "";
            return JSON.stringify({emptySecretBlocked, oneSubmit, retry,
                successive, identity, disappeared, nextFlow, cancelled});
        }
    }
    LazyLoader {
        id: dialogLoader
        active: Quickshell.screens.length > 0
        PolkitDialog { requestFlow: root.shownFlow; hostScreen: Quickshell.screens[0] }
    }
}
