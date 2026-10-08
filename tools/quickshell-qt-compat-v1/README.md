# QuickShell 0.3.1 et Qt 6.12

Ce dossier conserve les **sources de construction**, jamais le binaire compilé.
Il dérive du `PKGBUILD` officiel Arch `extra/quickshell 0.3.1-1` : `pkgrel=1.1`
identifie la reconstruction locale, et `prepare()` applique le correctif amont
fusionné dans [Quickshell PR 1002](https://github.com/quickshell-mirror/quickshell/pull/1002).
Le fichier `changelog/next.md` de cette PR n'existe pas dans l'archive `v0.3.1` ;
le patch conservé ici ne contient que ses changements de code applicables.

## Pourquoi

Le paquet officiel du 21 août 2026 a été construit avec Qt 6.11.2. Après le
passage du système à Qt 6.12.0, QuickShell signale ce décalage au démarrage.
Une reconstruction sans correctif échoue aussi à la compilation `moc` sur des
métatypes incomplets dans les modules Hyprland et I3/Sway. Le correctif amont
résout ces erreurs sans désactiver de module.

## Dépendances et construction

En plus des dépendances d'exécution déclarées dans `PKGBUILD`, la construction
demande `base-devel`, `cli11`, `cmake`, `ninja`, `qt6-shadertools`,
`spirv-tools`, `vulkan-headers` et `wayland-protocols`. Installer les
dépendances de compilation par le gestionnaire de paquets selon la politique de
la machine ; `makepkg -s` peut les demander. Ne pas utiliser une version de Qt
différente de celle qui sera chargée à l'exécution.

Depuis ce dossier :

```sh
makepkg --verifysource
makepkg --cleanbuild --syncdeps
sha256sum quickshell-0.3.1-1.1-x86_64.pkg.tar
pacman -Qip quickshell-0.3.1-1.1-x86_64.pkg.tar
```

La construction du 8 octobre 2026 a utilisé les sources amont `v0.3.1`
(SHA-256 vérifié par `makepkg`) et le patch de ce dossier. `cli11 2.7.2-1`
était absent du système : son paquet Arch signé a été vérifié par `gpgv`, puis
extrait dans un préfixe de construction utilisateur. Dans ce cas particulier,
`makepkg --nodeps` a ignoré uniquement le contrôle de présence système de
`cli11` ; CMake a trouvé ses en-têtes dans ce préfixe. Ce contournement de
**construction** ne s'applique jamais à l'installation du paquet QuickShell.

Le paquet produit a été conservé hors dépôt sous
`~/.cache/quickshell-qt-compat-v1/`, avec le SHA-256
`68d75a1421d4d78ea1ab72f00194788298b275e58933b48dfa86aace596df2a5`.
Une reconstruction future peut produire un hash différent, même à partir des
mêmes sources ; vérifier toujours les métadonnées et les dépendances du nouvel
artefact. Installer uniquement par Pacman, sans copie manuelle de fichiers.

## Maintenance et retour arrière

Après une mise à jour de Qt, vérifier d'abord si Arch fournit un paquet
QuickShell plus récent construit pour cette version. Sinon, reconstruire avec
le Qt installé et le correctif encore nécessaire. Si Arch intègre le correctif
dans une nouvelle version, revenir au paquet officiel. La révision locale
`0.3.1-1.1` ne sera pas remplacée automatiquement par l'ancien `0.3.1-1` ;
surveiller les versions du dépôt.

Avant une installation, conserver le paquet officiel précédent dans le cache
Pacman et relever l'état du service. Un retour à `0.3.1-1` est possible par
Pacman, mais ce paquet reste compilé contre Qt 6.11.2 : sous Qt 6.12, il ne
constitue pas un retour à la compatibilité. En cas de régression, garder les
journaux, identifier la cause et ne réinstaller l'ancien paquet que si son
fonctionnement est jugé plus sûr que celui du nouveau.
