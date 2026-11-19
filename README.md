# 🎮 Minestrator-Restart

[Minestrator](https://minestrator.com) propose un hébergement gratuit de serveur Minecraft, mais coupe le serveur de force **toutes les 4 heures**. Ce projet contourne cette limite en redémarrant le serveur automatiquement, pour le garder en ligne en continu.

Une **plage de maintenance silencieuse de 1h à 6h du matin (heure de Paris)** est respectée : pendant cette plage, le script ne relance pas le serveur (voir plus bas).

## 🔐 Configuration des Secrets

**Settings → Secrets and variables → Actions → New repository secret**, ajouter :

| Nom du secret | Obligatoire | Description | Exemple |
|---|---|---|---|
| `MINESTRATOR_ACCOUNT` | ✅ Oui | 🧾 Email + mot de passe Minestrator, séparés par une virgule | `monemail@example.com,monmotdepasse` |
| `MINESTRATOR_SERVER_ID` | ✅ Oui | 🖥️ ID du serveur | `123456` |
| `MINESTRATOR_AUTH` | ✅ Oui | 🔑 Token d'autorisation API, avec le préfixe Bearer | `Bearer xxxxxxxxxxxxxxxx` |
| `GOST_PROXY` | ✅ Oui | 🌐 Adresse du proxy Gost — les IP de GitHub Actions sont détectées comme VPN et bloquent la connexion, ce secret est donc indispensable | `socks5://user:pass@1.2.3.4:1080` |
| `TG_BOT` | ⬜ Optionnel | 📨 Notification Telegram : Chat ID et Bot Token séparés par une virgule | `987654321,123456:AAFxxx` |
| `DISCORD_WEBHOOK` | ⬜ Optionnel | 📣 URL d'un webhook Discord pour recevoir les notifications de redémarrage dans un salon | `https://discord.com/api/webhooks/xxx/yyy` |


## 🕐 Horaires d'exécution

Le workflow tourne **toutes les heures** (`0 * * * *`). À chaque exécution, le script vérifie l'heure actuelle à Paris :

- **Entre 1h et 6h du matin** : le script ne clique pas sur Redémarrer/Démarrer. Le serveur peut donc s'éteindre tout seul au bout de 4h et rester hors ligne — c'est voulu.
- **À partir de 6h** : le script reprend normalement et redémarre/relance le serveur comme d'habitude.

(Le calcul utilise le fuseau `Europe/Paris`, donc l'heure d'été/hiver est gérée automatiquement.)

## 📣 Webhook Discord

Oui, c'est possible : en renseignant le secret `DISCORD_WEBHOOK`, le script envoie automatiquement un message dans le salon Discord relié au webhook à chaque exécution (succès, échec, ou "pas d'action pendant la plage 1h-6h").

En plus du webhook, le script écrit deux fichiers à la racine du dépôt avec l'estimation du prochain arrêt forcé (déduite du compte à rebours affiché par Minestrator) :

- `restart_schedule.json` — pour lecture humaine / debug :
  ```json
  {
    "next_restart_utc": "2026-11-19T18:42:00Z",
    "next_restart_epoch": 1795123200,
    "seconds_remaining": 8040,
    "updated_utc": "2026-11-19T14:40:03Z",
    "frozen": false
  }
  ```
- `restart_schedule.txt` — format minimal pour Skript, sans dépendre d'un addon JSON :
  ```
  frozen=0;seconds_remaining=8040
  ```

Ces fichiers sont commités automatiquement par le workflow, ce qui les rend accessibles publiquement via leur URL "raw" GitHub, par exemple :
`https://raw.githubusercontent.com/Romain2506/Minestrator-Restart/main/restart_schedule.txt`

## 🧩 Annonces in-game avec Skript

Un plugin Minestrator (Skript) ne peut pas "recevoir" un webhook Discord entrant (les webhooks Discord sont à sens unique : vers Discord uniquement). La solution retenue est donc :

1. Le script Python calcule `seconds_remaining` (temps restant avant la coupure forcée) et le publie dans `restart_schedule.json` (voir ci-dessus).
2. Un script Skript interroge cette URL **toutes les 5 minutes** et resynchronise un compte à rebours interne (`{restart::countdown}`), qui descend ensuite de lui-même chaque minute.
3. Il déclenche :
   - une annonce à **5 minutes** avant le redémarrage,
   - une annonce finale au moment du redémarrage.
4. Comme le workflow GitHub ne tourne pas en continu, le compte à rebours est une **variable Skript persistante**, donc il continue à descendre correctement même entre deux exécutions du workflow.

**Addon requis côté serveur : [Reqn](https://github.com/btk5h/reqn/releases)** (léger, juste pour l'HTTP).
SkBee **ne fait pas** de requêtes HTTP (NBT, scoreboards, structures... rien côté web) — ce n'est donc pas lui qu'il faut pour ça. Pour éviter de dépendre d'un addon JSON en plus, le fichier distant est au format texte tout simple (`frozen=0;seconds_remaining=8040`), lu avec la fonction native Skript `split at` — aucun addon JSON n'est nécessaire.

**Commande incluse** : `/prochainredemarrage` (alias `/restarttime`, `/nextrestart`), protégée par la permission `minestrator.restart.info`, donne à un joueur/OP le temps restant avant le prochain redémarrage.

Voir `skript/announce_restart.sk` fourni dans ce dépôt.
