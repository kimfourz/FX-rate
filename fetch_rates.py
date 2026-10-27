"""Open Exchange Rates에서 환율을 받아 rates.json으로 저장합니다.
GitHub Actions가 정해진 시간에 자동으로 실행합니다.
API 키는 GitHub Secrets(OXR_APP_ID)에 저장되며 파일에는 남지 않습니다.
"""
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

APP_ID = os.environ.get("OXR_APP_ID", "").strip()
if not APP_ID:
    sys.exit("OXR_APP_ID secret이 설정되지 않았습니다.")

URL = "https://openexchangerates.org/api/latest.json?app_id=" + APP_ID

try:
    with urllib.request.urlopen(URL, timeout=30) as resp:
        data = json.load(resp)
except urllib.error.HTTPError as e:
    # 주소(API 키 포함)는 로그에 남기지 않음
    sys.exit(f"환율 조회 실패: HTTP {e.code}")
except Exception as e:
    sys.exit(f"환율 조회 실패: {type(e).__name__}")

rates = data.get("rates") or {}
if "EUR" not in rates:
    sys.exit("환율 응답 형식이 예상과 다릅니다.")

KST = datetime.timezone(datetime.timedelta(hours=9))
now = datetime.datetime.now(datetime.timezone.utc)
rate_time = datetime.datetime.fromtimestamp(data["timestamp"], datetime.timezone.utc)

out = {
    "source": "Open Exchange Rates",
    "rate_time_kst": rate_time.astimezone(KST).strftime("%Y-%m-%d %H:%M"),
    "fetched_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    "fetched_at_kst": now.astimezone(KST).strftime("%Y-%m-%d %H:%M"),
    # 1 단위 통화 = ? USD  (계산기의 usdPerUnit과 같은 의미)
    "usd_per_unit": {c: round(1 / v, 10) for c, v in sorted(rates.items()) if v},
}

with open("rates.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)

print(f"저장 완료: 환율 기준 {out['rate_time_kst']} KST, 통화 {len(out['usd_per_unit'])}개")
