# Kanjium 日语声调数据

`accents.tsv` 是原始 `accents.txt` 的逐字节副本。124,137 条记录，3,350,542 字节；多个读音、表记各占一条，不能把记录数当去重后的词数。

- 上游：[mifunetoshiro/kanjium](https://github.com/mifunetoshiro/kanjium)
- 固定版本：`685d4d723d6d20bf9beb169103aeac188eb067ad`（声调文件提交于 2024-06-16）
- 下载时间：2026-10-31
- 格式：UTF-8 TSV，依次为词形、假名读音、声调核位置；多个变体用逗号分隔，0 表示平板型。
- [许可：CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)，完整许可证保存在 LICENSE.txt。
- 归属：The pitch accent notation was provided by Uros O. through the free Kanjium database.

版本、来源 URL、SHA-256 和归属记录在 metadata.json。程序首次使用时校验 SHA-256，并缓存词形与读音索引；查询不需要联网。数据校验失败或文件缺失时保留失败记录，继续尝试 OJAD、U-biq。

以后替换数据时同时更新 metadata.json 的版本、来源和校验信息，保留许可证与归属；程序不会在制卡时静默下载或覆盖数据。
