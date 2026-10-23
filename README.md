# NixOS ZFS / Umbriel + Noctalia v5 installer

[![Build and test installer ISO](https://github.com/keewai704/nixos-installer-zfs/actions/workflows/build-iso.yml/badge.svg)](https://github.com/keewai704/nixos-installer-zfs/actions/workflows/build-iso.yml)

公式NixOSのグラフィカルISO共通モジュールを土台に、**Umbriel + ネイティブ版Noctalia v5**のライブデスクトップと、ZFS用GUIインストールウィザードを組み込んだx86_64向けISOです。起動すると自動ログインし、インストーラーが開きます。インストール先もUmbriel + Noctalia v5を使います。

## 構成

- [Umbriel](https://github.com/noctalia-dev/umbriel): Waylandコンポジター
- [Noctalia v5](https://github.com/noctalia-dev/noctalia): ネイティブのデスクトップシェル（v4のQuickshell版ではありません）
- [xddxdd/nix-cachyos-kernel](https://github.com/xddxdd/nix-cachyos-kernel): `linuxPackages-cachyos-latest`と対応する`zfs_cachyos`
- [sadjow/claude-code-nix](https://github.com/sadjow/claude-code-nix)の`claude`と[sadjow/codex-cli-nix](https://github.com/sadjow/codex-cli-nix)の`codex`
- Git、GitHub CLI (`gh`)、Firefox、Foot、ネットワーク設定GUI、パーティション管理ツール
- 日本語/英語、US/JISキーボード、ユーザー作成、ディスク選択と消去確認を備えたZFS用GUI

すべての入力は`flake.lock`で固定します。Noctaliaは現在5.3.0で、v5であることをNixのassertionでも確認します。CachyOS側のNixpkgsをNixOS本体にも使い、Umbriel・Noctalia側の入力は上流のまま保持して公式Cachixと一致させます。

## ISOの取得

1. [Actions](https://github.com/keewai704/nixos-installer-zfs/actions/workflows/build-iso.yml)の成功した実行を開きます。
2. Artifactsの`nixos-zfs-cachyos-x86_64-linux`をダウンロードして展開します。
3. `sha256sum -c SHA256SUMS`でISOを検証します。

検証に合格したISOだけをこの名前でアップロードします。ZIPにはISO、SHA256、`versions.json`、`verification.json`、デスクトップの検証画像が入ります。Artifactsの保持期間は14日です。

## GUIからインストール

**選択したディスク全体を消去します。UEFI起動、32 GiB以上の未使用ディスク、インターネット接続が必要です。既存パーティションの保持・暗号化・ミラー・デュアルブートはこのウィザードの対象外です。ISO自体はBIOSでもデスクトップまで起動できます。**

1. USB/ISOをUEFIモードで起動します。UmbrielとNoctalia v5に自動ログインし、ウィザードが開きます。
2. 必要ならNoctaliaのネットワークパネル、またはウィザードの「ネットワーク接続を設定」から接続します。
3. インストール先を容量・モデル・シリアル番号と照合して選択します。
4. ホスト名、ユーザー名、8文字以上のパスワード、言語・キーボード・タイムゾーンを設定します。
5. 内容を確認し、消去への同意と`ERASE /dev/実際のディスク名`の完全一致入力後、「インストール開始」を押します。
6. 完了画面でUSB/ISOを取り外して再起動し、作成したユーザーでGUIログインします。

ウィザードはNoctaliaのランチャーにある「NixOSをインストール (ZFS)」からも開けます。CLI操作は必要ありません。Claude CodeとCodexはFootから利用でき、それぞれ自分のアカウントで認証します。

| 領域 | 用途 |
|---|---|
| 先頭1 GiBのFAT32 ESP | `/boot`、systemd-boot |
| 残りのZFSプール`rpool` | ashift=12、zstd圧縮、atime無効 |
| `rpool/root` | `/` |
| `rpool/home` | `/home` |
| `rpool/nix` | `/nix` |

マウント済み、swap使用中、読み取り専用、アクティブなLUKS/RAIDやインポート済みZFSプールのメンバーであるディスクは拒否します。選択時のデバイス識別情報を消去直前にも照合します。プールには一意のPARTUUID、システムには新規の`networking.hostId`を使います。

GUIは一般ユーザーで実行し、権限を持つワーカーが検証済みの要求を受け取り、標準の`nixos-generate-config`と`nixos-install`を実行します。パスワードをコマンドライン引数やログ、flake、Nixストアに渡しません。yescryptのハッシュをインストール先の`/etc/user-passwords/ユーザー名`にroot専用の権限で保存します。rootログインはロックし、作成したユーザーがパスワード付きsudoを使います。ライブ環境の自動ログイン・パスワード不要sudoはインストール先へ引き継ぎません。

設定は`/etc/nixos`に残ります。以降の再構築は次で行えます。

```sh
sudo nixos-rebuild switch --flake /etc/nixos#installed
```

## キャッシュとビルド

Nix公式キャッシュに加え、次の署名付きキャッシュをActions・ISO・インストール先で共有します。URLと署名鍵は[nix/binary-caches.conf](nix/binary-caches.conf)で管理し、署名検証を維持します。

- `cache.xinux.uz`: [上流で案内されたCachyOSミラー](https://github.com/xddxdd/nix-cachyos-kernel/issues/89)
- `claude-code.cachix.org`・`codex-cli.cachix.org`: sadjow
- `umbriel.cachix.org`: [Umbriel公式](https://docs.noctalia.dev/umbriel/installation/#binary-cache)
- `noctalia.cachix.org`: [Noctalia公式](https://docs.noctalia.dev/noctalia/getting-started/nixos/)

UmbrielとNoctaliaは`cachix`ブランチのビルド済みコミットを固定し、各上流のNixpkgsを上書きしません。2026-10-23に両パッケージがそれぞれの公式Cachixから取得できることを確認しました。キャッシュにない依存パッケージはソースからビルドします。xddxddの旧Atticキャッシュは[停止報告](https://github.com/xddxdd/nix-cachyos-kernel/issues/110)があるため使用しません。

ビルドしたライブ環境・インストール先のパッケージは、ロックファイル単位のGitHub ActionsキャッシュにもVMテスト前に保存します。PRからは書き込みません。

Linux上でのビルド:

```sh
export NIX_CONFIG="$(cat nix/binary-caches.conf)"
nix --extra-experimental-features 'nix-command flakes' flake check --no-build --no-write-lock-file
nix --extra-experimental-features 'nix-command flakes' build .#iso --no-write-lock-file -L -o result-iso
```

## 自動検証

`push`・`pull_request`・手動実行で、読み取り専用のGitHubトークンとNixサンドボックスを使ってビルドします。外部ActionsはコミットSHAで固定しています。

配布する実際のISOをQEMUで起動し、次を検証します。

1. BIOS/UEFIでUmbriel、Noctalia v5、GUIウィザードが起動すること。CachyOS、対応ZFS、指定の4つのCLIが動くこと。
2. QEMUのキーボード入力でGUIのディスク選択・ユーザー作成・確認画面を操作すること。不正な消去文字列ではディスクが変化しないこと。
3. GUI自身が実際の`nixos-install`を実行し、ZFSへのインストールが完了すること。
4. ISOを外し、ネットワークなしでインストール先から起動できること。作成したユーザーのパスワードでログインし、Umbriel + Noctalia v5が起動すること。
5. ZFSの`/`・`/home`・`/nix`と保存データ、プールの正常性、CLI、失敗したsystemdユニットがないこと。

使い捨てのQCOW2ディスクだけをVMに接続します。実機のブロックデバイスは渡しません。インストール中だけQEMUのユーザーネットワークを使い、ポートは転送しません。テストでもGUIでパスワードを設定し、rootのロックを維持します。シリアルログと画面キャプチャを別のArtifactにも保存します。実機固有のストレージ・Wi-Fi・GPU・Secure Bootの互換性はVM検証の対象外です。

再現:

```sh
nix build .#iso -o result-iso -L
nix develop .#ci --command python tests/iso_install.py --iso result-iso/iso/nixos-zfs-cachyos-x86_64-linux.iso
```

`.vm-test`には検証結果と画像を残します。再実行は`--work-dir`で空の別ディレクトリを指定してください。KVMがなければTCGを使います。依存の更新は`nix flake update`で行い、Actionsの検証に合格したISOを使ってください。
