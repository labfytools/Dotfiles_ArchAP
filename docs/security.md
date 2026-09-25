# Sécurité

## Politique de versionnement

Ne jamais versionner, même temporairement :

- clés Atuin et bases/store Atuin ;
- clés privées SSH ;
- clés privées GPG ;
- tokens et clés API ;
- mots de passe et cookies ;
- `.netrc` ;
- credentials Rclone ;
- credentials GitHub ou Forgejo ;
- secrets Nextcloud ;
- credentials Proton, WireGuard ou autres applications ;
- bases applicatives et historiques personnels.

Un `.gitignore` limite les erreurs courantes, mais ne constitue pas une
protection suffisante. Avant chaque publication, inspecter le diff, les
nouveaux fichiers et les motifs de credentials sans jamais afficher leur
valeur dans un rapport.

## Stockage local

Les secrets et données runtime appartiennent à la machine locale ou à une
sauvegarde chiffrée externe. Ils ne doivent pas être placés dans un package
Stow public. Les permissions doivent être restrictives, particulièrement pour
les clés privées, `.netrc`, stores de credentials et clé Atuin.

Les unités ou scripts peuvent référencer le chemin d'une configuration locale,
mais ne doivent ni embarquer son contenu ni journaliser ses secrets.

## Historique Git

Supprimer un fichier du dernier commit ne le retire pas des anciens objets
Git. Lorsqu'un secret a été commité, la réponse correcte est :

1. considérer le secret comme compromis ;
2. le révoquer ou le faire tourner ;
3. préserver les sauvegardes nécessaires hors dépôt ;
4. purger le chemin de tout l'historique ;
5. vérifier les objets et toutes les refs avant publication.

L'historique de `Dotfiles_ArchAP` a été assaini pendant la préparation de la
version `0.1.0`, notamment pour retirer les anciennes données locales qui ne
devaient pas être publiées. Cette mention ne révèle ni ancienne valeur, ni
empreinte sensible, ni emplacement de sauvegarde.

## Contrôles avant publication

```bash
git status --short
git diff --check
git diff --cached --check
git fsck --full --no-dangling
```

Compléter ces contrôles par une recherche prudente de types de secrets dans le
HEAD et l'historique. Les rapports doivent seulement indiquer le fichier, le
type potentiel, sa présence actuelle ou historique et l'action recommandée ;
ils ne doivent jamais reproduire la valeur détectée.

## Dépôt public et licence

Le miroir GitHub est public. Toute donnée commitée doit donc être considérée
comme publiable immédiatement. Le dépôt ne possède actuellement aucune
licence ; cette absence n'autorise pas implicitement la réutilisation du
contenu.
