# private-isu

「[ISUCON](https://isucon.net)」は、LINE株式会社の商標または登録商標です。

本リポジトリが書籍の題材になりました。詳しくは以下のURLをご覧ください。

* [達人が教えるWebパフォーマンスチューニング 〜ISUCONから学ぶ高速化の実践：書籍案内｜技術評論社](https://gihyo.jp/book/2022/978-4-297-12846-3)
* [tatsujin-web-performance/tatsujin-web-performance: 達人が教えるWebパフォーマンスチューニング〜ISUCONから学ぶ高速化の実践](https://github.com/tatsujin-web-performance/tatsujin-web-performance)

ハッシュタグ： `#ISUCON本`

## タイムライン

2016年に作成した社内ISUCONリポジトリを2021年に手直ししました。2022年に書籍の題材になりました。

［2016年開催時のブログ］

* ISUCON6出題チームが社内ISUCONを開催！AMIも公開！！ - pixiv inside [archive] https://devpixiv.hatenablog.com/entry/2016/05/18/115206
* 社内ISUCONを公開したら広く使われた話 - pixiv inside [archive] https://devpixiv.hatenablog.com/entry/2016/09/26/130112

過去ISUCON公式で練習問題として推奨されたことがある。

* ISUCON初心者のためのISUCON7予選対策 : ISUCON公式Blog https://isucon.net/archives/50697356.html

［2021年開催時のブログ］

* 社内ISUCON “TIMES-ISUCON” を開催しました！ | PR TIMES 開発者ブログ https://developers.prtimes.jp/2021/06/04/times-isucon-1/

## ディレクトリ構成

```
├── app.py           # Flaskアプリケーション (Python実装)
├── pyproject.toml   # Python依存関係 (uv)
├── Dockerfile       # アプリケーションコンテナ
├── compose.yml      # Docker Compose設定
├── sql/             # PostgreSQLスキーマ・データ
├── templates/       # Jinja2テンプレート
├── public/          # 静的ファイル (CSS, JS, 画像)
├── etc/nginx/       # Nginx設定
├── benchmarker/     # ベンチマーカーのソースコード
└── provisioning/    # Ansibleプレイブック
```

* [manual.md](/manual.md)は当日マニュアル。一部社内イベントを意識した記述があるので注意すること。
* [public_manual.md](/public_manual.md) は事前公開レギュレーション

## OS

Ubuntu 24.04

## 対応言語と状況

本フォークでは、以下の言語による参考実装のみを提供しています。
* Python (Flask + gunicorn)

データベースはMySQLから **PostgreSQL 17** に移行されています。

## 起動方法

**重要:** 以下のいずれの手順を実行する前にも、まずプロジェクトのルートディレクトリで `make init` を実行して初期データを準備してください。

* Docker Composeを利用したローカル開発を推奨します。

### AMI

セキュリティアップデートは行われないため、自己責任で利用してください。

* 競技者用インスタンスでは、セキュリティグループでTCP/80番ポートへのアクセスを許可する必要があります。
  * EC2インスタンス作成時のネットワーク設定で「インターネットからのHTTPトラフィックを許可する」といったオプションにチェックを入れても構いません。
* ベンチマーカー用インスタンスには、コンピューティング最適化インスタンスなど、十分なスペックのマシンを利用することを推奨します。

ベンチマーカーインスタンス上での実行方法

```sh
$ sudo su - isucon
$ /home/isucon/private_isu.git/benchmarker/bin/benchmarker -u /home/isucon/private_isu.git/benchmarker/userdata -t http://<target IP>
```

競技者用インスタンス上でのベンチマーカー実行方法

```sh
$ sudo su - isucon
$ /home/isucon/private_isu/benchmarker/bin/benchmarker -u /home/isucon/private_isu/benchmarker/userdata -t http://localhost
```

起動直後はRubyの参考実装が動作しています。他の言語を使用する場合は、[`manual.md`](/manual.md)を参照して必要な作業を行ってください。

現在配布しているAMIは、競技者用インスタンスにベンチマーカーを同梱したものです。

以下のAMI IDで起動できます（リージョンは `ap-northeast-1` （アジアパシフィック (東京)））。これは特定日時のスナップショットのため、より新しいAMIが利用可能になっている場合があります。AWSコンソールで最新情報を確認することをお勧めします。推奨インスタンスタイプは、競技者用が`c7a.large`、ベンチマーカー用が`c7a.xlarge`です。

競技者用 (Ubuntu 24.04, amd64): [`catatsuy_private_isu_amd64_20250615`](https://ap-northeast-1.console.aws.amazon.com/ec2/home?region=ap-northeast-1#ImageDetails:imageId=ami-002d61d6436f85f12)

### 手元で動かす

**注意:** いずれの手順も、ディスク容量に十分な空きがあるマシン上で行ってください。

* アプリケーションは、Python、PostgreSQL、memcachedがインストールされていれば動作するはずです。
* ベンチマーカーは、Goの実行環境と`userdata`ディレクトリがあれば動作します。
* Docker Composeを使用する場合は、メモリを潤沢に搭載したマシンで実行してください。

#### MacやLinux上で適当に動かす

PostgreSQLとmemcachedを起動した上で、以下の手順を実行してください。

1. PostgreSQL用データを準備:
```sh
make init
```

2. PostgreSQLにデータをロード:
```sh
make restore
```

補足: `script/bootstrap` の自動チェック/修復で使うSQLヘルパーは、DB名/ユーザー/パスワードを `isuconp` 固定で扱います。

3. アプリケーションを起動:
```sh
uv sync
.venv/bin/gunicorn app:app -b 0.0.0.0:8080
```

4. ベンチマーカーを実行:
```sh
cd benchmarker
make
./bin/benchmarker -t "http://localhost:8080" -u ./userdata
# Output
# {"pass":true,"score":1710,"success":1434,"fail":0,"messages":[]}
```

#### Docker Compose

起動前に`sql/isuconp_data.dump`（PostgreSQLロード用データ）が配置されている必要があります。`make init`で生成できます。初回起動時は`script/restore`がこのdumpを`pg_restore`します。

```sh
docker compose up
```

##### ポートの競合

このDocker Composeによる環境ではTCPのポート80と5432をホストにマッピングする設定になっています。ホスト側で別のプロセスがポート80と5432を使用していると起動できないため、それらのプロセスがある場合は一旦停止するか、`compose.yml`を編集してマッピングするポートを変更する必要があります。

ポートを変更する場合は、`compose.yml`内の`services`以下、`nginx`と`postgres`のセクションに定義されている`ports`の定義を変更してください。ホスト側のポート80, 5432をそれぞれ8080, 15432に変更する場合は、次のように修正します。

```yaml
services:
  nginx:
    # 略
    ports:
      - "80:80"
  postgres:
    # 略
    ports:
      - "5432:5432"
```

```yaml
services:
  nginx:
    # 略
    ports:
      - "8080:80" # nginxがホストに開くポートを8080に変更
  postgres:
    # 略
    ports:
      - "15432:5432" # postgresがホストに開くポートを15432に変更
```

##### 変更の反映

`compose.yml`や言語実装の変更を反映するためには、`docker compose down`で一旦停止し、再度`docker compose up --build`で起動し直してください。`--build`オプションを付与することで、アプリケーションコンテナのイメージが再構築され、言語実装の変更が反映されます。

ベンチマーカーは以下の手順で実行できます。

```sh
cd benchmarker
docker build -t private-isu-benchmarker .
docker run --network host -i private-isu-benchmarker /bin/benchmarker -t http://host.docker.internal -u /opt/userdata
# Linuxの場合
docker run --network host --add-host host.docker.internal:host-gateway -i private-isu-benchmarker /bin/benchmarker -t http://host.docker.internal -u /opt/userdata
```

`host.docker.internal`で動作しない場合は、`ip a`コマンドなどで`docker0`インタフェースに割り当てられたホスト側のIPアドレスを確認し、`host.docker.internal`の代わりにそのIPアドレスを指定してください。例えば、以下の出力の場合は`172.17.0.1`を指定します。

```
3: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN group default
    link/ether 02:42:ca:63:0c:59 brd ff:ff:ff:ff:ff:ff
    inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0
       valid_lft forever preferred_lft forever
    inet6 fe80::42:caff:fe63:c59/64 scope link
       valid_lft forever preferred_lft forever
```

### cloud-init を利用して環境を構築する

matsuu氏が提供する[`cloud-init`に対応したISUCON過去問題環境構築用のcloud-config集](https://github.com/matsuu/cloud-init-isucon/)を利用して、競技者用およびベンチマーカーインスタンスを構築できます。

`cloud-init`に対応した多様な環境（例: AWS、Azure、Google Cloud、Oracle Cloud、さくらのクラウド、Multipass、VMwareなど）、つまりクラウドからローカル環境まで幅広く対応しています。

Apple Silicon搭載のマシン上でローカル環境を構築する場合、Multipassの利用を推奨します。

https://github.com/matsuu/cloud-init-isucon/tree/main/private-isu

ISUCON過去問題の環境を「さくらのクラウド」で構築する | さくらのナレッジ https://knowledge.sakura.ad.jp/31520/

### Cloud Formationを利用して構築する

https://gist.github.com/tohutohu/024551682a9004da286b0abd6366fa55 を参照

### 競技者用・ベンチマーカーインスタンスのセットアップ方法

自身でインスタンスをセットアップしたい場合は、`provisioning/`ディレクトリ以下のスクリプトを参照してください。

## 事例集

* [インフラ研修 | Progate Path](https://app.path.progate.com/tasks/8ybBQYEXl73ajnNRGc-E0/preview)
  * この問題を新卒研修で利用する場合の事前研修に利用しています
* private-isuのベンチマーカーをLambdaで実行する仕組みを公開しました | PR TIMES 開発者ブログ https://developers.prtimes.jp/2024/01/29/private-isu-bench-lambda/
* 日本CTO協会による合同ISUCON研修の紹介 - Pepabo Tech Portal https://tech.pepabo.com/2024/02/16/isucon-2023/

## 他の言語実装

* Rust実装 https://github.com/Romira915/private-isu-rust
* Scala実装 https://github.com/catatsuy/private-isu/pull/140
