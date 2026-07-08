# GSC Slack Leaderboard

ระบบดึงข้อมูลจริงจาก Google Search Console แล้วโพสต์ SEO MTD Leaderboard เข้า Slack

## เว็บในรอบแรก

รอบแรกเอา `bslclinic.com` ออกจากลูปก่อน เหลือ 9 เว็บ:

1. globalengr.com
2. crestphuket.com
3. ionenergy.co.th
4. dchhospital.com
5. drchenhospital.com
6. changconsumer.com
7. sa-logistics.co.th
8. aescon.co.th
9. aesovation.com

## Logic รายงาน

ระบบใช้ข้อมูลแบบ Month-to-Date เทียบกับช่วงเดียวกันของเดือนก่อน

ตัวอย่าง:
- ถ้ารันวันที่ 8 Jul และตั้ง data delay = 2 วัน
- ข้อมูลปัจจุบัน = 1–6 Jul
- เทียบกับ = 1–6 Jun

Metrics ที่ใช้:
- Clicks
- Impressions

ไม่ใช้:
- CTR
- Avg Position
- Top 3
- Top 10

## ติดตั้ง

```bash
pip install -r requirements.txt
```

## Environment Variables

ต้องมีอย่างน้อย:

```bash
SLACK_WEBHOOK_URL=...
GOOGLE_SERVICE_ACCOUNT_JSON=...
```

หรือใช้แบบ Base64:

```bash
GOOGLE_SERVICE_ACCOUNT_JSON_BASE64=...
```

ค่าแนะนำ:

```bash
REPORT_TZ=Asia/Bangkok
GSC_DATA_DELAY_DAYS=2
MIN_CLICKS_FOR_STATUS=5
MIN_IMPRESSIONS_FOR_STATUS=100
```

## รันทดสอบ

```bash
python gsc_slack_report.py
```

ถ้าไม่ได้ใส่ `SLACK_WEBHOOK_URL` ระบบจะ print รายงานออกมาเฉย ๆ ยังไม่ส่งเข้า Slack

## Claude Routine Instructions

ใส่ในช่อง Instructions:

```text
Run the Google Search Console SEO MTD leaderboard script.

Command:
python gsc_slack_report.py

Rules:
- Use only real Google Search Console data from the script.
- Do not invent or estimate numbers.
- The report must include Website, Clicks, Impressions, and Thai status only.
- Do not include CTR, average position, Top 3, or Top 10.
- If a site fails because of permissions, keep running other sites and show the warning from the script.
- Post the report to Slack using the configured Slack webhook.
```

## Setup Script ใน Claude Routine

```bash
python -m pip install -r requirements.txt
```

## Schedule

แนะนำ:
- Daily
- 09:00 เวลาไทย
