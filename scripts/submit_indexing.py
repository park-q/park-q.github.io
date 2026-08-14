"""Google Indexing API로 URL 색인 생성을 일괄 요청한다.

사용법:
    python scripts/submit_indexing.py <service-account-key.json> [--dry-run]

sitemap.xml에서 URL을 직접 읽으므로 목록을 따로 관리할 필요가 없다.
"""

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

# Windows 콘솔 기본 코드페이지에서 한글이 깨지지 않도록 고정한다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCOPES = ["https://www.googleapis.com/auth/indexing"]
ENDPOINT = "https://indexing.googleapis.com/v3/urlNotifications:publish"
SITEMAP = Path(__file__).resolve().parent.parent / "public" / "sitemap.xml"
NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
DELAY_SECONDS = 1.0


def load_urls(sitemap: Path) -> list[str]:
    if not sitemap.exists():
        sys.exit(f"sitemap을 찾을 수 없습니다: {sitemap}\n먼저 `hugo --gc --minify`를 실행하세요.")
    root = ET.parse(sitemap).getroot()
    return [loc.text.strip() for loc in root.findall(".//sm:url/sm:loc", NS) if loc.text]


def submit(session: AuthorizedSession, url: str) -> tuple[bool, str]:
    body = {"url": url, "type": "URL_UPDATED"}
    try:
        resp = session.post(ENDPOINT, json=body, timeout=30)
    except requests.RequestException as exc:
        return False, f"요청 실패: {exc}"

    if resp.status_code == 200:
        return True, "OK"

    # 오류 본문에서 사람이 읽을 메시지를 뽑아낸다.
    try:
        message = resp.json()["error"]["message"]
    except (ValueError, KeyError):
        message = resp.text[:200]
    return False, f"HTTP {resp.status_code}: {message}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Google Indexing API 일괄 제출")
    parser.add_argument("key_file", help="서비스 계정 JSON 키 파일 경로")
    parser.add_argument("--dry-run", action="store_true", help="제출 없이 대상 URL만 출력")
    args = parser.parse_args()

    urls = load_urls(SITEMAP)
    print(f"대상 URL {len(urls)}개 (출처: {SITEMAP})\n")

    if args.dry_run:
        for url in urls:
            print(f"  {url}")
        print("\n[dry-run] 실제로 제출하지 않았습니다.")
        return 0

    key_path = Path(args.key_file)
    if not key_path.exists():
        sys.exit(f"키 파일을 찾을 수 없습니다: {key_path}")

    credentials = service_account.Credentials.from_service_account_file(
        str(key_path), scopes=SCOPES
    )
    session = AuthorizedSession(credentials)
    print(f"서비스 계정: {credentials.service_account_email}\n")

    failures: list[tuple[str, str]] = []
    for i, url in enumerate(urls, 1):
        ok, detail = submit(session, url)
        status = "성공" if ok else "실패"
        print(f"[{i:>2}/{len(urls)}] {status}  {url}")
        if not ok:
            print(f"         └ {detail}")
            failures.append((url, detail))
        if i < len(urls):
            time.sleep(DELAY_SECONDS)

    succeeded = len(urls) - len(failures)
    print(f"\n{'=' * 60}")
    print(f"집계: 총 {len(urls)}개 | 성공 {succeeded}개 | 실패 {len(failures)}개")

    if failures:
        print(f"\n실패한 URL {len(failures)}개:")
        for url, detail in failures:
            print(f"  {url}")
            print(f"    └ {detail}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
