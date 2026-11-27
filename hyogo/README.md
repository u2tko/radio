# `#兵庫クリーンラジオ` アーカイブ（`hyogo/`）

兵庫県政に関するラジオ配信 `#兵庫クリーンラジオ` の配信台本、分析・年表ノート、および一次資料（兵庫県知事記者会見議事録）を管理するディレクトリです。

## ディレクトリ構成

| パス | 内容 | 入口・詳細 |
|---|---|---|
| `analysis/` | アーカイブ横断棚卸し・通史年表・周辺事件整理ノート | [analysis/README.md](./analysis/README.md) |
| `kaiken/` | 2026年兵庫県知事記者会見の公式議事録アーカイブ・発言分析・外部書き起こし突合 | [kaiken/README.md](./kaiken/README.md) |
| `2026-09/` | 2026年9月期の配信原稿（12本） | — |
| `2026-10/` | 2026年10月期の配信原稿（13本） | — |
| `2026-11/` | 2026年11月期の配信原稿（28本） | — |
| `outline/` | 初期設計・テンプレート資料（4本 ※現行標準は2026年11月完成形） | — |

## AI・執筆時の主な参照先

1. **全体像・過去回・周辺事件の把握**
   - [統合時系列年表＆周辺事件整理ノート（2024年3月〜2026年11月）](./analysis/2024-2026_timeline_and_incidents.md)
   - [原稿アーカイブ棚卸し＆変遷分析レポート（2026年9月〜11月・全53本）](./analysis/202609-11_inventory_and_evolution.md)
2. **公式発言の一次資料確認**
   - [2026年 知事記者会見 議事録一覧](./kaiken/2026/README.md)
   - [2026年 知事発言キーワード・アピール軸の推移分析](./kaiken/analysis/2026_rhetoric_shift.md)
3. **適用ルール・ワークフロー**
   - 全体ルール（README同期）：[repo-readme-sync.md](../.agents/rules/repo-readme-sync.md)
   - 編集方針・最新フォーマット・検証規律：[hyogo-clean-radio.md](../.agents/rules/hyogo-clean-radio.md) / [hyogo-radio-core.md](../.agents/rules/hyogo-radio-core.md)
   - スキル：[hyogo-script-draft](../.agents/skills/hyogo-script-draft/SKILL.md) / [hyogo-archive-analysis](../.agents/skills/hyogo-archive-analysis/SKILL.md)
