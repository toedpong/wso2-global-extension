# wso2-global-extension

WSO2 API Manager global mediation extensions ที่ใช้เก็บ request/response ของ API ในรายการ migration
(`MigrationAPIList.xml`) ลง PostgreSQL เพื่อนำไปใช้เป็น fixture สำหรับ unit test ตอน migrate PI → CPI

## Sequences

| ไฟล์ | หน้าที่ |
| --- | --- |
| `WSO2AM--Ext--In.xml` / `WSO2AM--Ext--Out.xml` | Global In/Out sequence ที่เรียก sequence ด้านล่าง |
| `Send-Header-Seq.xml` | ใส่ header `X-Application-Name`, `X-User-ID`, `X-Client-ID` ให้ backend |
| `Custom-DBLogger-In-Seq.xml` | ถ้า API อยู่ใน list และเก็บยังไม่ถึง 10 ครั้ง → INSERT request (method, URL, path, headers ทั้งหมดเป็น JSON, body) |
| `Custom-DBLogger-Out-Seq.xml` | UPDATE row เดิมด้วย response (status, headers เป็น JSON, body, เวลาที่ใช้) แล้วเพิ่ม count |
| `MigrationAPIList.xml` | Local entry รายชื่อ `API_NAME` ที่ต้องการเก็บ |

Header ที่เป็น credential (`Authorization`, `Cookie`, `Set-Cookie`, `X-API-Key`) จะถูก mask เป็น `***MASKED***`

## Database

สร้าง/อัปเกรดตารางด้วย `sql/schema.sql` (รันซ้ำได้)

```sh
psql -h <host> -p <port> -U cpiadmin -d cpidev -f sql/schema.sql
```

## Export fixtures สำหรับ unit test

```sh
pip install psycopg2-binary
export PGHOST=<host> PGPORT=<port> PGDATABASE=cpidev PGUSER=cpiadmin PGPASSWORD=<password>
python tools/export_fixtures.py --out fixtures --completed-only            # ทุก API
python tools/export_fixtures.py --out fixtures --api OR_HR_ZHRHRI001        # เฉพาะบาง API
```

ได้ไฟล์ `fixtures/<API_NAME>/<message_id>.json` รูปแบบ

```json
{
  "api": { "name": "OR_HR_ZHRHRI001", "version": "1.0" },
  "request": { "method": "POST", "url": "...", "path": "/...", "headers": { "...": "..." }, "body": { } },
  "expected_response": { "status": 200, "headers": { "...": "..." }, "body": { } },
  "captured": { "message_id": "...", "request_time": "...", "execution_time_ms": 123, "...": "..." }
}
```

ใช้ `request` ยิงเข้า iFlow บน CPI แล้วเทียบผลกับ `expected_response`
