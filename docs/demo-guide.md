# デモ手順書

ローカル環境でブランド信頼観測システムのデモを実行する手順。

---

## 前提条件

- Docker Desktop がインストール・起動済みであること
- ポート 5432（PostgreSQL）と 8080（API）が空いていること

---

## 1. 起動

```bash
cd C:\Git\subjective-trust-platform

# 起動（初回はビルドに数分かかる）
docker compose up --build -d

# 起動確認（3サービスが Running になること）
docker compose ps
```

API が起動するまで約10秒待ってからヘルスチェック：

```bash
curl http://localhost:8080/health
# → {"status":"ok","environment":"local","ai_backend":"mock"}
```

---

## 2. デモデータ投入

```bash
docker compose exec api python scripts/seed_demo.py
```

以下が投入される：
- 店舗 3 件（渋谷店・新宿店・銀座店）
- スタッフ 6 名（各店舗 2 名）
- 来店記録 15 件（各店舗 5 件）
- アンケート回答 9 件（自由記述コメント付き）
- 外部レビュー 6 件（Google 口コミ想定）
- 信頼スコアスナップショット 3 件（各店舗 1 件）

---

## 3. Swagger UI を開く

ブラウザで以下を開く：

```
http://localhost:8080/docs
```

全エンドポイントの一覧と実行フォームが表示される。以下のデモはすべて Swagger UI 上で実行できる。

---

## 4. デモ操作手順（Swagger UI）

### Step 1: 店舗一覧を確認する

1. `GET /stores` を開く
2. **Try it out** をクリック
3. **Execute** をクリック

渋谷店・新宿店・銀座店の 3 店舗が JSON で表示される。

---

### Step 2: 信頼スコアを確認する

1. `GET /stores/{store_id}/scores` を開く
2. **Try it out** をクリック
3. `store_id` に以下のいずれかを入力して **Execute**

| 店舗 | store_id | 特徴 |
|---|---|---|
| 渋谷店 | `10000000-0000-0000-0000-000000000001` | 接客信頼が高い（service: 62.5） |
| 新宿店 | `10000000-0000-0000-0000-000000000002` | 接客信頼が低い（service: 45.3） |
| 銀座店 | `10000000-0000-0000-0000-000000000003` | データ不足で `unreliable: true` |

**見どころ：**
- 渋谷店は接客信頼（service_score: 62.5）が高い → 丁寧な接客の高評価が多い
- 新宿店は接客信頼（service_score: 45.3）が低い → 「押し売り感」のフィードバックが影響
- 銀座店は event_count=18（閾値 20 未満）で `unreliable: true` → コールドスタート期の表示

---

### Step 3: 接客タグを入力する

1. `POST /visits` を開く
2. **Try it out** をクリック
3. Request body に以下を貼り付けて **Execute**

```json
{
  "store_id": "10000000-0000-0000-0000-000000000001",
  "visit_purpose": "gift",
  "contact_result": "purchase"
}
```

4. レスポンスから `visit_id` をコピーする（次のステップで使う）

**ポイント：** 接客タグ入力は `visit_purpose`（来店目的）と `contact_result`（接客結果）の 2 項目のみ。現場スタッフが 10 秒以内で入力できる設計。

---

### Step 4: アンケートを送信する

1. `POST /feedback` を開く
2. **Try it out** をクリック
3. Request body に以下を貼り付け、`visit_id` を Step 3 でコピーした値に差し替えて **Execute**

```json
{
  "visit_id": "<Step 3 でコピーした visit_id>",
  "score_consultation": 5,
  "score_information": 4,
  "score_revisit": 5,
  "free_comment": "ギフト選びの相談に親身に乗ってもらえました"
}
```

**確認ポイント：**
- `interpretation_queued: true` → 自由記述が AI 解釈パイプラインにキュー登録された
- `score_consultation` / `score_information` / `score_revisit` は 1〜5 の 5 段階
- `free_comment` が AI 解釈の入力になる（AI_BACKEND=mock でモック解釈結果を返す）

---

### Step 5: 欠品離脱のケースを入力する

1. `POST /visits` を開く
2. Request body に以下を貼り付けて **Execute**

```json
{
  "store_id": "10000000-0000-0000-0000-000000000002",
  "visit_purpose": "purchase",
  "contact_result": "out_of_stock_exit",
  "alternative_proposed": false
}
```

**ポイント：**
- `contact_result: "out_of_stock_exit"` → 欠品による離脱
- `alternative_proposed: false` → 代替提案がなかった
- このパターンはルールベースで **提案信頼のネガティブ TrustEvent** が自動生成される
- 欠品離脱以外で `alternative_proposed` を指定するとバリデーションエラーになる（条件付きフィールド）

---

### Step 6: スコアを再確認する

1. `GET /stores/{store_id}/scores` で渋谷店のスコアを再確認
2. 新宿店のスコアも確認し、店舗間の差を比較する

---

## 5. デモで説明するストーリー

### ストーリーの流れ

```
1. 店舗ごとに信頼スコアが異なる
   → 売上データだけでは見えない「顧客の主観的な信頼」を可視化

2. 接客タグ入力はたった 2 項目
   → 現場スタッフの負荷を最小化（10 秒以内）

3. アンケートの自由記述を AI が自動解釈
   → 「なぜそう感じたか」を 5 次元 × 感情極性 × 深刻度に構造化

4. 欠品時に代替提案がないと信頼が毀損
   → ルールベースで自動検知し、改善アクションにつなげる

5. データ不足の店舗は「参考値」と明示
   → コールドスタート期の誤った判断を防ぐ
```

### 信頼の 5 次元

| 次元 | 問い | デモでの確認方法 |
|---|---|---|
| 商品信頼（product） | 品質・価格への納得感 | 渋谷店: 55.2 / 銀座店: 58.5 |
| 接客信頼（service） | 安心して相談できるか | 渋谷店: 62.5（高） / 新宿店: 45.3（低） |
| 提案信頼（proposal） | 自分に合った提案か | 銀座店: 42.0（欠品で低下） |
| 運営信頼（operation） | 在庫・案内に齟齬がないか | 新宿店: 47.5 |
| 物語信頼（story） | ブランドらしさの一貫性 | 銀座店: 65.0（高） |

---

## 6. 停止

```bash
# 停止（データは保持）
docker compose down

# 停止 + データ削除（完全リセット）
docker compose down -v
```

---

## 店舗 ID 一覧

| 店舗名 | store_id |
|---|---|
| 渋谷店 | `10000000-0000-0000-0000-000000000001` |
| 新宿店 | `10000000-0000-0000-0000-000000000002` |
| 銀座店 | `10000000-0000-0000-0000-000000000003` |

---

## トラブルシューティング

**API が応答しない場合：**
```bash
docker compose logs api --tail=20
```

**DB 接続エラーの場合：**
```bash
docker compose logs db --tail=10
docker compose exec db pg_isready -U trust_user -d trust_platform
```

**データをリセットしたい場合：**
```bash
docker compose down -v
docker compose up -d
# 10秒待ってからシード
docker compose exec api python scripts/seed_demo.py
```
