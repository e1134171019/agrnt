# 網頁爬蟲調度模組（初版）
# 依 feeds.yml 配置抓取 type: web 的來源
# 建議安裝: pip install requests beautifulsoup4

import requests
from bs4 import BeautifulSoup

def fetch_web_source(source):
    """
    根據 feeds.yml 的 web source 配置抓取內容
    source: dict, 包含 url, selector, fields, limit 等
    回傳: list[dict], 每則標準化內容
    """
    url = source["url"]
    selector = source.get("selector")
    fields = source.get("fields", {})
    limit = source.get("limit", 10)
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select(selector)
    results = []
    for item in items[:limit]:
        entry = {}
        for k, v in fields.items():
            if v.endswith("::attr(href)"):
                # 支援 a::attr(href) 這種語法
                sel = v.split("::attr(")[0]
                attr = v.split("::attr(")[1].rstrip(")")
                tag = item.select_one(sel)
                entry[k] = tag[attr] if tag and tag.has_attr(attr) else None
            else:
                tag = item.select_one(v)
                entry[k] = tag.get_text(strip=True) if tag else None
        entry["source_key"] = source["key"]
        entry["category"] = source.get("category")
        results.append(entry)
    return results

if __name__ == "__main__":
    # 測試用: 可直接執行本檔案
    import yaml
    with open("ops/feeds.yml", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    for src in config["sources"]:
        if src.get("type") == "web" and src.get("enabled"):
            print(f"[Web] 抓取 {src['name']} ...")
            data = fetch_web_source(src)
            print(data)
