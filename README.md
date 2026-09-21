# wso2-global-extension

WSO2 API Manager global mediation extensions ที่ใช้เก็บ request/response ของ API ในรายการ migration
(`MigrationAPIList.xml`) ลง PostgreSQL เพื่อนำไปใช้เป็น fixture สำหรับ unit test ตอน migrate PI → CPI

## Sequences

| ไฟล์ | หน้าที่ |
| --- | --- |
| `WSO2AM--Ext--In.xml` / `WSO2AM--Ext--Out.xml` | Global In/Out sequence ที่เรียก sequence ด้านล่าง |
| `Send-Header-Seq.xml` | ใส่ header `X-Application-Name`, `X-User-ID`, `X-Client-ID` ให้ backend |
| `Custom-DBLogger-In-Seq.xml` | ถ้า API อยู่ใน list และเก็บยังไม่ถึง 10 ครั้ง → INSERT request (method, URL, path, headers ทั้งหมดเป็น JSON, body + format) |
| `Custom-DBLogger-Out-Seq.xml` | UPDATE row เดิมด้วย response (status, content-type, headers เป็น JSON, body + format, เวลาที่ใช้) แล้วเพิ่ม count |
| `Capture-Payload-Seq.xml` | แปลง body เป็น string ตาม Content-Type (ใช้ร่วมกันทั้งขา In/Out) |
| `MigrationAPIList.xml` | Local entry รายชื่อ `API_NAME` ที่ต้องการเก็บ |

### รูปแบบ payload ที่รองรับ (`REQUEST_FORMAT` / `RESPONSE_FORMAT`)

| Content-Type | format | สิ่งที่เก็บ |
| --- | --- | --- |
| `*json*` | `json` | JSON string (`json-eval($)`) |
| `*xml*`, `*soap*` | `xml` | XML/SOAP body |
| `application/x-www-form-urlencoded` | `form` | `<xformValues><field>value</field></xformValues>` (exporter แปลงเป็น dict) |
| `text/*` | `text` | ข้อความล้วน |
| อื่นๆ (octet-stream, multipart, pdf, …) | `binary` | base64 (exporter decode เป็นไฟล์ `.bin`) |
| ไม่มี body / 204 | `none` | `No Payload` |

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

ได้ไฟล์ `fixtures/<API_NAME>/<message_id>.json` (และ `<message_id>.request.xml|.bin`, `<message_id>.response.xml|.bin` สำหรับ XML/binary) รูปแบบ

```json
{
  "api": { "name": "OR_HR_ZHRHRI001", "version": "1.0" },
  "request": { "method": "POST", "url": "...", "path": "/...", "content_type": "application/json", "headers": { }, "body_format": "json", "body": { } },
  "expected_response": { "status": 200, "content_type": "text/xml", "headers": { }, "body_format": "xml", "body": "<...>", "body_file": "<message_id>.response.xml" },
  "captured": { "message_id": "...", "request_time": "...", "execution_time_ms": 123, "...": "..." }
}
```

ใช้ `request` ยิงเข้า iFlow บน CPI แล้วเทียบผลกับ `expected_response`
