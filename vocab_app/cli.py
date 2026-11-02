"""New entry point: offline previews by default; --live explicitly enables model calls."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

from vocab_app.settings import Settings, user_data_dir
from vocab_app.examples import OfflineClient
from vocab_app.providers import ModelClient
from vocab_app.pipeline import ImportPipeline
from vocab_app.preview import render_preview
from vocab_app.anki import AnkiClient

def main(argv=None):
    # Redirected Windows streams can default to a legacy ANSI code page.
    # Status messages must not turn successful generation/import into a failure.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="生成词卡预览；默认离线，不调用模型，不写 Anki。")
    parser.add_argument("--language", choices=["en", "ja", "ko"], default="en")
    parser.add_argument("--word", action="append", help="可重复传入多个词汇，含空格的短语请加引号")
    parser.add_argument("--provider", choices=["deepseek", "openai"])
    parser.add_argument("--model", help="实际 API 模型 ID；不是 ChatGPT 网页的模式名称")
    parser.add_argument("--tag-source", choices=["anki", "seed"], default=None, help="真实生成默认每批同步 Anki 标签；seed 使用产品初始表，离线默认 seed")
    parser.add_argument("--live", action="store_true", help="允许真实模型请求，可能产生费用")
    parser.add_argument("--pronunciation-source", choices=["none", "auto", "wiktionary", "free_dictionary", "cambridge", "oxford", "longman", "kanjium", "ojad", "ubiq", "krdict", "daum"], default=None, help="真实生成默认查找录音；日语声调依次查 Kanjium、OJAD、U-biq；离线默认关闭")
    parser.add_argument("--generation-mode", choices=["independent", "web", "sources"], default="independent")
    parser.add_argument("--sources", nargs="*", default=[], help="可选词典：wiktionary etymonline cambridge merriam_webster kotobank krdict")
    parser.add_argument("--image-source", choices=["none", "auto", "commons"], default=None,
                        help="真实生成默认从 Commons 自动选择第一张可用图片；none 关闭，离线默认关闭")
    parser.add_argument("--output-dir", type=Path, default=user_data_dir() / "previews")
    parser.add_argument("--import-anki", action="store_true", help="将指定的已审核预览写入 Anki")
    parser.add_argument("--import-preview", type=Path, help="要导入的既有 JSON 预览文件；不会重新生成")
    parser.add_argument("--deck", help="导入目标牌组；不存在时按该名称创建")
    parser.add_argument("--note-type", help="可选的既有兼容笔记类型；默认自动创建应用专用类型")
    args = parser.parse_args(argv)
    if args.import_anki:
        if not args.import_preview or not args.deck or args.live:
            parser.error("导入必须指定 --import-preview 和 --deck，且不可同时生成 --live。")
        try:
            note = json.loads(args.import_preview.read_text(encoding="utf-8-sig"))
            options = {"model": args.note_type} if args.note_type else {}
            note_id = AnkiClient().add_preview(note, args.deck, media_root=args.import_preview.parent, **options)
            print("已导入笔记：" + str(note_id))
            return 0
        except (ValueError, RuntimeError, OSError, KeyError, TypeError):
            print("导入失败：请检查预览格式、标签审核、牌组与字段。")
            return 1
    if args.import_preview:
        parser.error("--import-preview 必须配合 --import-anki 使用。")
    words = args.word or [{"en": "apple", "ja": "猫", "ko": "나무"}[args.language]]
    try:
        from .request_trace import recording_transport
        client = ModelClient(Settings.from_env(args.provider, args.model), recording_transport(args.output_dir / 'requests')) if args.live else OfflineClient()
        if args.live:
            client.settings.require_model()
        from vocab_app.public_media import PublicMediaRegistry, download_assets
        from vocab_app.media import MediaResult
        from vocab_app.taxonomy import TagCatalog
        tag_source = args.tag_source or ("anki" if args.live else "seed")
        catalog = TagCatalog.from_anki(AnkiClient()) if tag_source == "anki" else TagCatalog.load()
        pipeline = ImportPipeline(client, PublicMediaRegistry(), tag_catalog=catalog)
        failed = 0
        for index, word in enumerate(words, 1):
            try:
                pronunciation_source = args.pronunciation_source or ("auto" if args.live else "none")
                image_source = args.image_source or ("auto" if args.live else "none")
                note = pipeline.generate(word, args.language, pronunciation_source, image_source, args.generation_mode, args.sources)
                args.output_dir.mkdir(parents=True, exist_ok=True)
                for group in ("pronunciation", "images"):
                    note[group] = download_assets(MediaResult(**note[group]), args.output_dir / "media").to_dict()
                if args.language == "en" and pronunciation_source == "auto" and not note["pronunciation"]["assets"]:
                    note["pronunciation"] = PublicMediaRegistry().english_audio(word, args.output_dir / "media").to_dict()
                digest = hashlib.sha256((args.language + ":" + word).encode()).hexdigest()[:12]
                stem = args.output_dir / (args.language + "-" + digest)
                stem.with_suffix(".json").write_text(json.dumps(note, ensure_ascii=False, indent=2), encoding="utf-8")
                stem.with_suffix(".html").write_text(render_preview(note), encoding="utf-8")
                print(str(index) + ": 预览已保存到 " + str(stem.with_suffix(".html")))
            except (ValueError, RuntimeError, OSError) as error:
                failed += 1
                print(str(index) + ": 失败 — " + str(error))
        return 1 if failed else 0
    except (ValueError, RuntimeError) as error:
        print(str(error))
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
