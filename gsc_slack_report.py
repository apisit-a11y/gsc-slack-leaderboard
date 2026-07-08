import base64
import calendar
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


@dataclass
class SiteResult:
    domain: str
    gsc_property: str
    current_clicks: int
    previous_clicks: int
    current_impressions: int
    previous_impressions: int
    clicks_change_pct: Optional[float]
    impressions_change_pct: Optional[float]
    status: str
    error: Optional[str] = None


def getenv_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{name} must be an integer, got: {value}")


def load_service_account_info() -> Dict[str, Any]:
    """
    Supports either:
    1) GOOGLE_SERVICE_ACCOUNT_JSON = raw JSON string
    2) GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 = base64-encoded JSON string
    """
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    raw_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")

    if raw_json:
        return json.loads(raw_json)

    if raw_b64:
        decoded = base64.b64decode(raw_b64).decode("utf-8")
        return json.loads(decoded)

    raise RuntimeError(
        "Missing Google credential. Set GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_JSON_BASE64."
    )


def build_gsc_service():
    info = load_service_account_info()
    credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("searchconsole", "v1", credentials=credentials, cache_discovery=False)


def pct_change(current: int, previous: int) -> Optional[float]:
    if previous == 0:
        if current == 0:
            return 0.0
        return None
    return ((current - previous) / previous) * 100


def fmt_num(value: int) -> str:
    return f"{value:,}"


def fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "ใหม่"
    rounded = round(value)
    sign = "+" if rounded > 0 else ""
    return f"{sign}{rounded}%"


def format_metric(value: int, change_pct: Optional[float]) -> str:
    return f"{fmt_num(value)} ({fmt_pct(change_pct)})"


def last_day_of_month(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def previous_month(year: int, month: int) -> Tuple[int, int]:
    if month == 1:
        return year - 1, 12
    return year, month - 1


def report_periods(today: Optional[date] = None) -> Tuple[date, date, date, date]:
    tz_name = os.getenv("REPORT_TZ", "Asia/Bangkok")
    data_delay_days = getenv_int("GSC_DATA_DELAY_DAYS", 2)

    if today is None:
        now = datetime.now(ZoneInfo(tz_name))
        today = now.date()

    stable_end = today - timedelta(days=data_delay_days)
    current_start = stable_end.replace(day=1)
    current_end = stable_end

    prev_year, prev_month = previous_month(current_start.year, current_start.month)
    prev_start = date(prev_year, prev_month, 1)
    prev_end_day = min(current_end.day, last_day_of_month(prev_year, prev_month))
    prev_end = date(prev_year, prev_month, prev_end_day)

    return current_start, current_end, prev_start, prev_end


def gsc_query(service, site_url: str, start_date: date, end_date: date) -> Dict[str, int]:
    body = {
        "startDate": start_date.isoformat(),
        "endDate": end_date.isoformat(),
        "rowLimit": 1,
    }

    response = service.searchanalytics().query(siteUrl=site_url, body=body).execute()
    rows = response.get("rows", [])

    if not rows:
        return {"clicks": 0, "impressions": 0}

    row = rows[0]
    return {
        "clicks": int(round(row.get("clicks", 0))),
        "impressions": int(round(row.get("impressions", 0))),
    }


def decide_status(
    current_clicks: int,
    previous_clicks: int,
    current_impressions: int,
    previous_impressions: int,
    clicks_pct: Optional[float],
    impressions_pct: Optional[float],
) -> str:
    min_clicks = getenv_int("MIN_CLICKS_FOR_STATUS", 5)
    min_impressions = getenv_int("MIN_IMPRESSIONS_FOR_STATUS", 100)

    if (current_clicks + previous_clicks) < min_clicks and (current_impressions + previous_impressions) < min_impressions:
        return "⚠️ ข้อมูลน้อย ยังสรุปไม่ได้"

    if clicks_pct is None:
        return "🟢 เติบโตดีมาก"

    if impressions_pct is None:
        impressions_pct = 0.0

    if clicks_pct <= -15 or (clicks_pct < -5 and impressions_pct < -5):
        return "🔴 ลดลงชัดเจน"

    if clicks_pct < -5 and impressions_pct > 5:
        return "🟡 การมองเห็นเพิ่ม แต่คลิกลด"

    if -15 < clicks_pct < -5:
        return "🟡 คลิกลด ต้องติดตาม"

    if clicks_pct >= 25:
        return "🟢 เติบโตดีมาก"

    if clicks_pct >= 5:
        return "🟢 เติบโต"

    return "⚪ ทรงตัว"


def load_sites(path: str = "sites.json") -> List[Dict[str, str]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def collect_results(service, sites: List[Dict[str, str]], current_start: date, current_end: date, previous_start: date, previous_end: date) -> List[SiteResult]:
    results: List[SiteResult] = []

    for site in sites:
        domain = site["domain"]
        gsc_property = site["gsc_property"]

        try:
            current = gsc_query(service, gsc_property, current_start, current_end)
            previous = gsc_query(service, gsc_property, previous_start, previous_end)

            current_clicks = current["clicks"]
            previous_clicks = previous["clicks"]
            current_impressions = current["impressions"]
            previous_impressions = previous["impressions"]

            clicks_change = pct_change(current_clicks, previous_clicks)
            impressions_change = pct_change(current_impressions, previous_impressions)

            status = decide_status(
                current_clicks,
                previous_clicks,
                current_impressions,
                previous_impressions,
                clicks_change,
                impressions_change,
            )

            results.append(
                SiteResult(
                    domain=domain,
                    gsc_property=gsc_property,
                    current_clicks=current_clicks,
                    previous_clicks=previous_clicks,
                    current_impressions=current_impressions,
                    previous_impressions=previous_impressions,
                    clicks_change_pct=clicks_change,
                    impressions_change_pct=impressions_change,
                    status=status,
                )
            )

        except HttpError as e:
            results.append(
                SiteResult(
                    domain=domain,
                    gsc_property=gsc_property,
                    current_clicks=0,
                    previous_clicks=0,
                    current_impressions=0,
                    previous_impressions=0,
                    clicks_change_pct=0.0,
                    impressions_change_pct=0.0,
                    status="⚠️ ดึงข้อมูลไม่ได้",
                    error=str(e)[:500],
                )
            )

        except Exception as e:
            results.append(
                SiteResult(
                    domain=domain,
                    gsc_property=gsc_property,
                    current_clicks=0,
                    previous_clicks=0,
                    current_impressions=0,
                    previous_impressions=0,
                    clicks_change_pct=0.0,
                    impressions_change_pct=0.0,
                    status="⚠️ ดึงข้อมูลไม่ได้",
                    error=str(e)[:500],
                )
            )

    results.sort(key=lambda x: (x.current_clicks, x.current_impressions), reverse=True)
    return results


def medal(rank: int) -> str:
    return {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, str(rank))


def thai_month_en(date_value: date) -> str:
    return date_value.strftime("%d %b %Y").lstrip("0")


def period_label(start: date, end: date) -> str:
    # Example: 1–6 Jul 2026
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {end.strftime('%b')} {end.year}"
    return f"{thai_month_en(start)} – {thai_month_en(end)}"


def build_slack_message(results: List[SiteResult], current_start: date, current_end: date, previous_start: date, previous_end: date) -> str:
    lines = []
    lines.append("🏆 SEO MTD Leaderboard – Google Search Console")
    lines.append(f"ข้อมูลปัจจุบัน: {period_label(current_start, current_end)}")
    lines.append(f"เทียบกับ: {period_label(previous_start, previous_end)}")
    lines.append("")
    lines.append("```")
    lines.append(f"{'#':<3} {'Website':<24} {'Clicks':<18} {'Impressions':<18} สถานะ")

    for index, item in enumerate(results, start=1):
        rank_label = medal(index)
        clicks_text = format_metric(item.current_clicks, item.clicks_change_pct)
        impressions_text = format_metric(item.current_impressions, item.impressions_change_pct)
        lines.append(f"{rank_label:<3} {item.domain:<24} {clicks_text:<18} {impressions_text:<18} {item.status}")

    lines.append("```")

    error_items = [item for item in results if item.error]
    if error_items:
        lines.append("")
        lines.append("⚠️ หมายเหตุ: มีบางเว็บที่ดึงข้อมูลไม่ได้")
        for item in error_items:
            lines.append(f"- {item.domain}: ตรวจสอบสิทธิ์ GSC หรือ property URL")

    return "\n".join(lines)


def post_to_slack(message: str):
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print(message)
        print("\nSLACK_WEBHOOK_URL is not set, so the report was printed only.")
        return

    response = requests.post(webhook_url, json={"text": message}, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(f"Slack webhook failed: {response.status_code} {response.text}")


def main():
    load_dotenv()

    sites_path = os.getenv("SITES_JSON_PATH", "sites.json")
    sites = load_sites(sites_path)

    current_start, current_end, previous_start, previous_end = report_periods()

    service = build_gsc_service()
    results = collect_results(service, sites, current_start, current_end, previous_start, previous_end)
    message = build_slack_message(results, current_start, current_end, previous_start, previous_end)

    print(message)
    post_to_slack(message)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
