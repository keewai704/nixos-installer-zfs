# NixOS ZFS + CachyOS installer

[![Build and test installer ISO](https://github.com/keewai704/nixos-installer-zfs/actions/workflows/build-iso.yml/badge.svg)](https://github.com/keewai704/nixos-installer-zfs/actions/workflows/build-iso.yml)

xddxddのCachyOSカーネルと、それに対応する`zfs_cachyos`を使う、x86_64向けNixOSインストーラーISOです。CLI形式で、インストール先はUEFI・単一ディスク・ZFSルートです。ISO自体はBIOS/UEFIの両方で起動できます。

## 含まれるもの

- [xddxdd/nix-cachyos-kernel](https://github.com/xddxdd/nix-cachyos-kernel)の`linuxPackages-cachyos-latest`と、同じパッケージセットの`zfs_cachyos`
- [sadjow/claude-code-nix](https://github.com/sadjow/claude-code-nix)のネイティブ版`claude`
- [sadjow/codex-cli-nix](https://github.com/sadjow/codex-cli-nix)のネイティブ版`codex`
- Git、GitHub CLI (`gh`)、curl、jq、ripgrep、nano、tmux、パーティション作成ツール
- ディスク消去前の確認を必須にした`install-zfs`
- インストール先でも同じカーネル・ZFS・CLIを使う、固定済みのflake一式

すべての入力は`flake.lock`で固定します。CachyOS側のNixpkgsを上書きせず、こちらのNixOSもそのリビジョンを使用します。CPU固有のv3/v4/Zen4向け最適化は指定せず、汎用x86_64版を使用します。各CLIの利用には自分のアカウントでの認証が必要です。

## ISOの取得

1. [Actions](https://github.com/keewai704/nixos-installer-zfs/actions/workflows/build-iso.yml)の成功した実行を開きます。
2. Artifactsの`nixos-zfs-cachyos-x86_64-linux`をダウンロードして展開します。
3. 同梱の`SHA256SUMS`でISOを検証します。

```sh
sha256sum -c SHA256SUMS
```

検証に合格したISOだけをこの名前でアップロードします。ZIPにはISO、SHA256、`versions.json`、`verification.json`が入ります。Artifactsの保持期間は14日です。

## ZFSへインストール

**選択したディスク全体を消去します。最低16 GiB、UEFI起動、インターネット接続が必要です。既存パーティションの保持、暗号化、ミラー、デュアルブートはこのヘルパーの対象外です。**

ISOをUSB等へ書き込み、UEFIモードで起動します。必要なら`nmtui`でネットワークを接続します。

```sh
lsblk -o NAME,SIZE,MODEL,SERIAL,FSTYPE,MOUNTPOINTS
ls -l /dev/disk/by-id/
sudo install-zfs --disk /dev/disk/by-id/実際のディスクID --hostname nixos
```

実ディスク名を表示して、例えば`ERASE /dev/nvme0n1`の入力を求めます。完全一致しない限りディスクを書き換えません。マウント済み・swap使用中・読み取り専用のディスクや、アクティブなLUKS/RAID等の子デバイスを持つディスクは拒否します。

作成する構成:

| 領域 | 用途 |
|---|---|
| 先頭1 GiBのFAT32 ESP | `/boot`、systemd-boot |
| 残りのZFSプール`rpool` | ashift=12、zstd圧縮、atime無効 |
| `rpool/root` | `/` |
| `rpool/home` | `/home` |
| `rpool/nix` | `/nix` |

プールのデバイスには一意のPARTUUIDを使用します。`networking.hostId`はインストールごとに新規生成します。ルートパスワードの設定後、アンマウントとプールのexportを行います。完了表示を確認してUSB/ISOを取り外し、再起動してください。

```sh
sudo reboot
```

設定を編集してからインストールしたい場合:

```sh
sudo install-zfs --disk /dev/disk/by-id/実際のディスクID --hostname nixos --prepare-only
sudo nano /mnt/etc/nixos/machine.nix
sudo nixos-install --flake /mnt/etc/nixos#installed
sudo umount -R /mnt
sudo zpool export rpool
sudo reboot
```

`hardware-configuration.nix`は実機で再生成され、`machine.nix`にはホスト名とhostIdが入ります。リポジトリ内の同名ファイルは評価用のサンプルです。実機へそのままコピーする代わりに`install-zfs`を使ってください。flakeは`modules/installed.nix`とこの2ファイルを読み込みます。`nixos-generate-config`が生成する`configuration.nix`は、このflakeによるインストールでは使用しません。

インストール後の設定は`/etc/nixos`に残り、以降は次で再構築できます。

```sh
sudo nixos-rebuild switch --flake /etc/nixos#installed
```

## ローカルビルド

Linux上のNixを使います。カーネルのソースビルドに備えて、十分なディスク容量とメモリを確保してください。

```sh
export NIX_CONFIG="$(cat nix/binary-caches.conf)"
nix --extra-experimental-features 'nix-command flakes' flake check --no-build --no-write-lock-file
nix --extra-experimental-features 'nix-command flakes' build .#iso --no-write-lock-file -L -o result-iso
ls result-iso/iso/
```

`cache.nixos.org`に加え、[上流で案内されているCachyOSミラー](https://github.com/xddxdd/nix-cachyos-kernel/issues/89)の`cache.xinux.uz`と、sadjowの`claude-code.cachix.org`・`codex-cli.cachix.org`を利用します。[nix/binary-caches.conf](nix/binary-caches.conf)の同じURL・署名鍵をActions、ISO、インストール先で共用します。署名検証は有効のままです。入力が一致するキャッシュがあればダウンロードし、なければソースからビルドします。

2026-10-23に、固定したカーネル・カーネルモジュール・ZFSのストアパスが`cache.xinux.uz`に存在することを確認しました。xddxddの旧Atticキャッシュには[停止報告](https://github.com/xddxdd/nix-cachyos-kernel/issues/110)があるため、そのURL・旧署名鍵は設定していません。キャッシュの利用可能性や、Nixpkgsの変更によるヒット率は保証されません。

ビルド済みパッケージはロックファイルごとにGitHub Actionsのキャッシュへ保存し、同じ入力を使う次回実行で再利用します。VMテストより先に保存するため、テストの修正時にもカーネルを毎回コンパイルする必要はありません。PRからはキャッシュを書き込みません。

## 自動検証

`push`、`pull_request`、手動実行で、読み取り専用のGitHubトークンとサンドボックスを使ってビルドします。外部Actionsは実在するリリースのコミットSHAで固定しています。

実際に配布するISOをQEMUで起動し、次を確認します。

1. BIOS起動とUEFI起動の両方で、CachyOSカーネル・対応するZFSモジュール・4つのCLIが動くこと。
2. 不正なディスク消去確認を拒否し、未フォーマットの仮想ディスクを変更しないこと。
3. UEFI環境で`install-zfs --prepare-only`を実行し、実際に生成されたflakeを`nixos-install`でZFSへインストールできること。
4. ISOを取り外した状態でインストール先から起動し、ZFSの`/`・`/home`・`/nix`、保存データ、CLI、プールの正常性、失敗したsystemdユニットがないこと。

UEFIでのインストール検証にはQEMUのユーザーネットワークを使い、実機での利用条件と同じく、固定済みの入力と設定済みの公開キャッシュを取得します。ポートの転送はありません。生成したflakeをVM内で評価・ビルドし、`nixos-install`でインストールします。BIOS起動と、ISOを外したインストール後の起動はNICなしで確認します。後者のテスト用にだけターゲットのコンソールパスワードを空にします。実機向け設定にはその変更を含めません。実機固有のストレージ・Wi-Fi・GPU・Secure Bootの互換性は、このVMテストの対象外です。

再現手順:

```sh
nix build .#iso -o result-iso -L
nix develop .#ci --command python tests/iso_install.py --iso result-iso/iso/nixos-zfs-cachyos-x86_64-linux.iso
```

`.vm-test`にはシリアルログと結果を残します。再実行は`--work-dir`で別の空ディレクトリを指定してください。KVMが利用できない環境ではTCGを使います。

更新は`nix flake update`で行い、Actionsの検証に合格したISOを使ってください。
