"""Awaiting Funds 계산 (balance.html 'Awaiting 계산기'와 같은 규칙)

사용: python3 awaiting_calc.py cc.txt settlement.txt rates.json
  cc.txt         : #settlement-currency_cloud 'CurrencyCloud balance status' 표
  settlement.txt : #settlement '모인 밸런스 요약'의 4번(송금중/Core-Ready) 부분
  rates.json     : 이 저장소의 환율 파일

계산 규칙
  C4 = Currencycloud 표에서 Sum이 마이너스인 통화만 USD로 환산해 합친 값 (부호 제거)
  W2 = 송금중 요약의 'WISE,USD' 합계 그대로
  N1 = 송금중 요약의 'NIUM,USD' 합계 그대로  (CURRENCY_CLOUD 송금중 금액은 제외)
  국가 = 통화 → 국가명 (NAMED에 없는 통화는 '코어국가')
  Awaiting이 0인 파트너는 줄을 뺌 (셋 다 0이면 'Awaiting Funds 없음')
"""
import datetime, json, re, sys

NAMED = {"USD": "미국", "EUR": "유럽", "GBP": "영국", "JPY": "일본", "CAD": "캐나다", "AUD": "호주", "MYR": "말레이시아"}
ORDER = ["미국", "유럽", "영국", "일본", "캐나다", "호주", "말레이시아"]
KNOWN = set("USD EUR GBP THB NZD HKD SGD CAD AUD IDR MYR CNY JPY PHP BRL PEN TRY INR VND KRW MXN ZAR PLN SEK NOK DKK CHF AED SAR".split())
KST = datetime.timezone(datetime.timedelta(hours=9))


def num(s):
    return float(s.replace(",", ""))


def fmt(n):
    return f"{n:,.2f}"


def parse_balance(text):
    rows = []
    for line in text.splitlines():
        codes = re.findall(r"[A-Z]{3}", line)
        ccy = next((c for c in codes if c in KNOWN), None)
        if not ccy:
            continue
        nums = re.findall(r"-?[\d,]+(?:\.\d+)?", line)
        nums = [n for n in nums if re.search(r"\d", n)]
        if not nums:
            continue
        rows.append((ccy, num(nums[-1])))
    return rows


def parse_remit(text):
    w2 = n1 = None
    wise, nium = [], []
    for line in text.splitlines():
        m = re.search(r"REMIT\s*,\s*(WISE|NIUM)\s*,\s*([A-Z]{3})\s+([\d,]+\.?\d*)", line, re.I)
        if m:
            (wise if m.group(1).upper() == "WISE" else nium).append(m.group(2).upper())
        m2 = re.search(r"(NIUM|WISE)\s*,\s*USD\s+([\d,]+\.?\d*)", line, re.I)
        if m2:
            if m2.group(1).upper() == "WISE":
                w2 = num(m2.group(2))
            else:
                n1 = num(m2.group(2))
    return w2, n1, wise, nium


def countries(ccys):
    named, core = [], False
    for c in ccys:
        if c in NAMED:
            if NAMED[c] not in named:
                named.append(NAMED[c])
        else:
            core = True
    out = [x for x in ORDER if x in named]
    if core:
        out.append("코어국가")
    return ", ".join(out)


def main(cc_path, st_path, rates_path):
    balance = parse_balance(open(cc_path, encoding="utf-8").read())
    st_text = open(st_path, encoding="utf-8").read()
    w2, n1, wise, nium = parse_remit(st_text)
    # 송금중 요약 자체는 찾았는데 파트너 줄이 없으면 = 그 파트너는 Awaiting 없음 (오류 아님)
    st_found = bool(re.search(r"송금중|Core-Ready|USD 합계", st_text))
    rj = json.load(open(rates_path, encoding="utf-8"))
    rates = dict(rj["usd_per_unit"])
    rates["USD"] = 1.0

    warns = []
    if not balance:
        warns.append("⚠ Currencycloud 잔액 표를 읽지 못했어요.")
    c4, c4ccys, missing, dust, detail = 0.0, [], [], [], []
    for ccy, s in balance:
        if s < 0:
            c4ccys.append(ccy)
            r = rates.get(ccy)
            if r is None:
                missing.append(ccy)
                continue
            usd = s * r
            c4 += usd
            detail.append(f"{ccy} {s:,.2f} × {r:.6f} = {fmt(usd)} USD")
            if abs(usd) < 100:
                dust.append(ccy)

    asof = datetime.datetime.now(KST).strftime("%m/%d %H:%M")
    # Awaiting이 없는(0인) 파트너는 줄을 빼고 표시
    lines = [f"파트너사별 Awaiting Funds ({asof} 기준)"]
    if round(abs(c4), 2) > 0:
        lines.append(f"• C4 {fmt(abs(c4))} USD ({countries(c4ccys)})")
    if w2:
        lines.append(f"• W2 {fmt(w2)} USD ({countries(wise)})")
    if n1:
        lines.append(f"• N1 {fmt(n1)} USD ({countries(nium)})")
    if len(lines) == 1:
        lines.append("• Awaiting Funds 없음")

    fetched = datetime.datetime.strptime(rj["fetched_at_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    age_h = (datetime.datetime.now(datetime.timezone.utc) - fetched).total_seconds() / 3600
    if age_h > 2:
        warns.append(f"⚠ 환율이 제때 업데이트되지 않아 이전 환율을 사용했어요 (조회 시각 {rj['fetched_at_kst']} KST).")
    if missing:
        warns.append(f"⚠ 환율이 없는 통화가 있어 C4에서 빠졌어요: {', '.join(missing)}")
    if not st_found:
        warns.append("⚠ #settlement 송금중 요약을 찾지 못해 W2/N1이 빠졌어요.")
    if dust:  # 소액 통화는 오류가 아니라서 Slack 메시지에는 넣지 않음
        print(f"참고: C4에 100 USD 미만 소액 통화 포함: {', '.join(dust)}", file=sys.stderr)

    # 표준출력(stdout) = Slack으로 보낼 메시지. 평소 4줄, 문제가 있을 때만 경고 줄 추가
    print("\n".join(lines + warns))
    # 계산 내역은 확인용으로 표준에러(stderr)에만 출력 (Slack으로 보내지 않음)
    print(f"환율: {rj['source']} (기준 {rj['rate_time_kst']} KST, 조회 {rj['fetched_at_kst']} KST)", file=sys.stderr)
    for d in detail:
        print(d, file=sys.stderr)


if __name__ == "__main__":
    main(*sys.argv[1:4])
