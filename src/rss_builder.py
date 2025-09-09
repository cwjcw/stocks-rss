from feedgen.feed import FeedGenerator
from datetime import datetime, timezone

def build_feed(meta: dict, items: list) -> str:
    fg = FeedGenerator()
    fg.title(meta["title"])
    fg.link(href=meta.get("link", ""), rel='alternate')
    fg.description(meta.get("description", ""))
    fg.language('zh-cn')
    for it in items:
        fe = fg.add_entry()
        fe.title(it["title"])
        fe.link(href=it.get("link", meta.get("link","")))
        fe.guid(it["guid"], permalink=False)
        fe.pubDate(it["pubdate"])
        fe.description(it["description"])
    return fg.rss_str(pretty=True).decode("utf-8")
