"""
PER 워크시트를 읽어와 정적 HTML 대시보드(index.html)로 빌드한다.

- 자격증명/스프레드시트 ID는 형제 프로젝트(gsheet-toss-portfolio-sync)와 동일하게 사용한다.
- 빈 행으로 구분된 종목 그룹을 그대로 보존하여 섹션으로 렌더링한다.
"""

import json
import os
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials


# === .env 자동 로드 ===
# 외부 의존성 없이 단순 KEY=VALUE 형식만 파싱한다.
def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(Path(__file__).resolve().parent / ".env")


# === 설정 ===
# 시트 ID 같은 민감 식별자는 환경 변수에서만 읽는다 (코드에 하드코딩 금지).
SPREADSHEET_ID = os.environ.get("PER_SPREADSHEET_ID")
if not SPREADSHEET_ID:
    raise SystemExit(
        "PER_SPREADSHEET_ID 환경 변수가 설정되어 있지 않습니다. "
        ".env 파일을 만들거나 export 하세요. (.env.example 참고)"
    )

SHEET_NAME = os.environ.get("PER_SHEET_NAME", "PER")
# 형제 프로젝트의 credentials.json 을 그대로 사용한다 (경로는 환경 변수로 override 가능).
CREDENTIALS_PATH = Path(
    os.environ.get(
        "PER_CREDENTIALS_PATH",
        "/Users/jerry/private/gsheet-toss-portfolio-sync/credentials.json",
    )
)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

OUT_DIR = Path(__file__).resolve().parent
OUT_HTML = OUT_DIR / "index.html"
OUT_JSON = OUT_DIR / "per_data.json"


def fetch_values() -> list[list[str]]:
    creds = Credentials.from_service_account_file(str(CREDENTIALS_PATH), scopes=SCOPES)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(SPREADSHEET_ID)
    ws = ss.worksheet(SHEET_NAME)
    return ws.get_all_values()


def parse(values: list[list[str]]) -> dict:
    """1행(그룹 헤더) + 2행(컬럼 헤더) + 데이터 + 환율 행 분리, 빈 행 기준 그룹화.

    A열 첫 셀이 `[...]` 형태(예: "[2025·26·27년 영업이익 출처/근거]")인 그룹을 만나면,
    그 라벨 그룹 자체와 이후의 모든 그룹을 **참고 섹션**으로 분리한다.
    (메인 PER 표는 이 라벨 이전의 그룹만으로 구성한다.)
    """
    header_top = values[0]
    header_mid = values[1]

    exchange_row = None
    cleaned: list[list[str]] = []
    for row in values[2:]:
        if row and row[0] == "총합/요약":
            exchange_row = row
            continue
        cleaned.append(row)

    all_groups: list[list[list[str]]] = []
    current: list[list[str]] = []
    for row in cleaned:
        if not any(c.strip() for c in row):
            if current:
                all_groups.append(current)
                current = []
            continue
        current.append(row)
    if current:
        all_groups.append(current)

    # `[...]` 라벨 그룹을 경계로 메인/참고 분리
    main_groups: list[list[list[str]]] = []
    reference_label = ""
    reference_groups: list[list[list[str]]] = []
    boundary_hit = False
    for grp in all_groups:
        first_cell = grp[0][0].strip() if grp and grp[0] else ""
        if not boundary_hit and first_cell.startswith("[") and first_cell.endswith("]"):
            boundary_hit = True
            reference_label = first_cell
            # 라벨만 들어있는 단독 그룹이면 reference_groups 에 포함하지 않는다.
            if len(grp) > 1:
                reference_groups.append(grp[1:])
            continue
        if boundary_hit:
            reference_groups.append(grp)
        else:
            main_groups.append(grp)

    # 환율 추출 (D열, index 3)
    exchange_rate = ""
    if exchange_row and len(exchange_row) > 3:
        exchange_rate = exchange_row[3]

    return {
        "header_top": header_top,
        "header_mid": header_mid,
        "groups": main_groups,
        "reference_label": reference_label,
        "reference_groups": reference_groups,
        "exchange_rate": exchange_rate,
    }


HTML_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>PER 대시보드</title>
<style>
  :root {{
    --bg: #0f1115;
    --panel: #161a22;
    --panel-2: #1c2230;
    --border: #2a3142;
    --text: #e6e8ee;
    --muted: #8b93a7;
    --accent: #7aa2ff;
    --pos: #34d399;
    --neg: #f87171;
    --warn: #fbbf24;
    --group-line: #3b4254;
  }}
  @media (prefers-color-scheme: light) {{
    :root {{
      --bg: #f6f7fb;
      --panel: #ffffff;
      --panel-2: #f1f3f9;
      --border: #d9dee8;
      --text: #1b2030;
      --muted: #6b7280;
      --accent: #2c5fff;
      --pos: #0f9d6e;
      --neg: #d83a3a;
      --warn: #b97400;
      --group-line: #c2c9d6;
    }}
  }}

  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: "Apple SD Gothic Neo", "Pretendard", -apple-system, BlinkMacSystemFont,
                 "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-feature-settings: "tnum" 1, "kern" 1;
  }}

  .page {{
    max-width: 1720px;
    margin: 0 auto;
    padding: 28px 24px 64px;
  }}

  header.top {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 18px;
  }}
  header.top h1 {{
    margin: 0;
    font-size: 22px;
    letter-spacing: -0.01em;
  }}
  header.top .meta {{
    color: var(--muted);
    font-size: 13px;
  }}
  header.top .meta b {{
    color: var(--text);
    font-weight: 600;
  }}

  .legend {{
    display: flex;
    gap: 14px;
    flex-wrap: wrap;
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 14px;
  }}
  .legend span::before {{
    content: "";
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 2px;
    margin-right: 6px;
    vertical-align: 1px;
    background: var(--accent);
  }}
  .legend .pos::before {{ background: var(--pos); }}
  .legend .neg::before {{ background: var(--neg); }}
  .legend .warn::before {{ background: var(--warn); }}

  .table-wrap {{
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: auto;
    box-shadow: 0 1px 0 rgba(0,0,0,0.06);
  }}

  table {{
    border-collapse: separate;
    border-spacing: 0;
    width: 100%;
    min-width: 1400px;
    font-size: 13px;
  }}

  thead th {{
    position: sticky;
    top: 0;
    z-index: 2;
    background: var(--panel-2);
    color: var(--text);
    text-align: right;
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
    font-weight: 600;
  }}
  thead tr.group-row th {{
    top: 0;
    text-align: center;
    font-size: 11px;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px dashed var(--border);
    padding: 6px 12px;
    background: var(--panel-2);
  }}
  thead tr.col-row th {{
    top: 28px;
  }}
  thead tr.col-row th.text-left {{ text-align: left; }}

  tbody td {{
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
    text-align: right;
    white-space: nowrap;
    vertical-align: middle;
  }}
  tbody td.name {{
    text-align: left;
    font-weight: 600;
  }}
  tbody td.ticker {{
    text-align: left;
    color: var(--muted);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }}
  tbody td.muted {{ color: var(--muted); }}

  tbody tr.group-sep td {{
    background: transparent;
    height: 14px;
    border-bottom: 2px solid var(--group-line);
    padding: 0;
  }}

  tbody tr:hover td {{ background: rgba(122,162,255,0.06); }}

  /* 그룹 헤더 셀 너비/구분선 */
  thead tr.group-row th + th {{ border-left: 1px solid var(--border); }}
  thead tr.col-row th.group-start {{ border-left: 1px solid var(--border); }}
  tbody td.group-start {{ border-left: 1px solid var(--border); }}

  .pos {{ color: var(--pos); }}
  .neg {{ color: var(--neg); }}
  .warn {{ color: var(--warn); }}

  .footer {{
    margin-top: 14px;
    color: var(--muted);
    font-size: 12px;
  }}

  /* 참고/근거 섹션 */
  section.reference {{
    margin-top: 28px;
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px 20px 22px;
  }}
  section.reference h2 {{
    margin: 0 0 14px;
    font-size: 15px;
    letter-spacing: -0.01em;
    color: var(--text);
  }}
  .ref-block + .ref-block {{ margin-top: 18px; }}
  .ref-table {{
    border-collapse: separate;
    border-spacing: 0;
    width: 100%;
    font-size: 12.5px;
  }}
  .ref-table th, .ref-table td {{
    padding: 6px 10px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
    text-align: left;
    white-space: normal;
    line-height: 1.45;
  }}
  .ref-table th {{
    background: var(--panel-2);
    color: var(--muted);
    font-weight: 600;
    font-size: 11.5px;
    letter-spacing: 0.02em;
  }}
  .ref-table td.first, .ref-table th.first {{
    font-weight: 600;
    color: var(--text);
    white-space: nowrap;
    width: 1%;
    padding-right: 16px;
  }}
  .ref-notes {{
    margin: 0;
    padding-left: 18px;
    color: var(--muted);
    font-size: 12.5px;
    line-height: 1.6;
  }}
  .ref-notes li {{ margin-bottom: 4px; }}
</style>
</head>
<body>
  <div class="page">
    <header class="top">
      <h1>PER 대시보드</h1>
      <div class="meta">
        환율 <b id="fx">{exchange_rate}</b> 원/달러 · 출처 시트 <b>PER</b>
      </div>
    </header>

    <div class="legend">
      <span class="pos">양(+) 변화</span>
      <span class="neg">음(-) 변화</span>
      <span class="warn">PER 100 이상 (고밸류 주의)</span>
    </div>

    <div class="table-wrap">
      <table id="per-table"></table>
    </div>

    <section id="reference-host"></section>

    <div class="footer">
      그룹은 원본 시트의 빈 행 구분을 그대로 따른다.
      셀이 비어 있는 종목은 해당 데이터가 시트에 입력되어 있지 않은 경우다.
    </div>
  </div>

<script>
const DATA = {data_json};

// 컬럼 그룹 정의 (인덱스 범위 inclusive)
const COL_GROUPS = [
  {{ label: "기본",           start: 0,  end: 1 }},
  {{ label: "가격",           start: 2,  end: 3 }},
  {{ label: "시가총액",       start: 4,  end: 5 }},
  {{ label: "PER",            start: 6,  end: 8 }},
  {{ label: "분기 실적 발표", start: 9,  end: 13 }},
  {{ label: "다음분기 가이던스", start: 14, end: 17 }},
  {{ label: "영업이익(연간)", start: 18, end: 20 }},
];

const COL_COUNT = DATA.header_mid.length;

function classifyValue(text) {{
  if (text == null) return "";
  const t = String(text).trim();
  if (!t) return "";
  // 백분율/배수 변동 표시: 시트에 이미 부호가 있는 경우
  if (/^-/.test(t)) return "neg";
  if (/^\\+/.test(t)) return "pos";
  return "";
}}

function classifyPER(text) {{
  if (!text) return "";
  // "154.2" 처럼 숫자만 들어있을 때 고PER 강조
  const n = parseFloat(String(text).replace(/[,\\s]/g, ""));
  if (!isFinite(n)) return "";
  if (n >= 100) return "warn";
  return "";
}}

function isYoYQoQ(colIdx) {{
  // 분기 실적 YoY/QoQ (12,13), 가이던스 YoY/QoQ (16,17)
  return colIdx === 12 || colIdx === 13 || colIdx === 16 || colIdx === 17;
}}

function isPERCol(colIdx) {{
  return colIdx === 6 || colIdx === 7 || colIdx === 8;
}}

function buildHead() {{
  const groupTr = document.createElement("tr");
  groupTr.className = "group-row";
  for (const g of COL_GROUPS) {{
    const th = document.createElement("th");
    th.colSpan = g.end - g.start + 1;
    th.textContent = g.label;
    groupTr.appendChild(th);
  }}

  const colTr = document.createElement("tr");
  colTr.className = "col-row";
  const groupStartCols = new Set(COL_GROUPS.map(g => g.start));
  for (let i = 0; i < COL_COUNT; i++) {{
    const th = document.createElement("th");
    th.textContent = DATA.header_mid[i] || "";
    if (i <= 1) th.classList.add("text-left");
    if (groupStartCols.has(i) && i !== 0) th.classList.add("group-start");
    colTr.appendChild(th);
  }}

  const thead = document.createElement("thead");
  thead.appendChild(groupTr);
  thead.appendChild(colTr);
  return thead;
}}

function buildBody() {{
  const tbody = document.createElement("tbody");
  const groupStartCols = new Set(COL_GROUPS.map(g => g.start));

  DATA.groups.forEach((rows, gi) => {{
    rows.forEach(row => {{
      const tr = document.createElement("tr");
      for (let i = 0; i < COL_COUNT; i++) {{
        const td = document.createElement("td");
        const val = row[i] || "";
        td.textContent = val;

        if (i === 0) td.classList.add("name");
        else if (i === 1) td.classList.add("ticker");

        if (groupStartCols.has(i) && i !== 0) td.classList.add("group-start");

        // 변화율 강조
        if (isYoYQoQ(i)) {{
          const cls = classifyValue(val);
          if (cls) td.classList.add(cls);
        }}
        // 고 PER 경고
        if (isPERCol(i)) {{
          const cls = classifyPER(val);
          if (cls) td.classList.add(cls);
        }}
        // 빈 값은 muted 처리
        if (!val) td.classList.add("muted");

        tr.appendChild(td);
      }}
      tbody.appendChild(tr);
    }});

    // 마지막 그룹이 아니면 그룹 구분선 행 추가
    if (gi !== DATA.groups.length - 1) {{
      const sep = document.createElement("tr");
      sep.className = "group-sep";
      const td = document.createElement("td");
      td.colSpan = COL_COUNT;
      sep.appendChild(td);
      tbody.appendChild(sep);
    }}
  }});

  return tbody;
}}

function buildReference() {{
  const host = document.getElementById("reference-host");
  host.innerHTML = "";
  const groups = DATA.reference_groups || [];
  if (!DATA.reference_label && groups.length === 0) {{
    host.style.display = "none";
    return;
  }}
  host.style.display = "";
  host.className = "reference";

  const h2 = document.createElement("h2");
  h2.textContent = DATA.reference_label || "참고";
  host.appendChild(h2);

  groups.forEach(grp => {{
    const block = document.createElement("div");
    block.className = "ref-block";

    // 의미 있는 컬럼 수 (가장 오른쪽 비어있지 않은 셀 + 1)
    const maxCols = grp.reduce((acc, row) => {{
      let last = 0;
      for (let i = 0; i < row.length; i++) {{
        if ((row[i] || "").trim()) last = i + 1;
      }}
      return Math.max(acc, last);
    }}, 0);

    if (maxCols <= 1) {{
      // 각주처럼 한 셀짜리 행들 → 리스트
      const ul = document.createElement("ul");
      ul.className = "ref-notes";
      grp.forEach(row => {{
        const li = document.createElement("li");
        li.textContent = (row[0] || "").replace(/^\\*\\s*/, "");
        ul.appendChild(li);
      }});
      block.appendChild(ul);
    }} else {{
      // 다중 컬럼 → 표. 첫 행은 헤더로.
      const table = document.createElement("table");
      table.className = "ref-table";
      const tbody = document.createElement("tbody");
      grp.forEach((row, ri) => {{
        const tr = document.createElement("tr");
        for (let i = 0; i < maxCols; i++) {{
          const cell = document.createElement(ri === 0 ? "th" : "td");
          cell.textContent = row[i] || "";
          if (i === 0) cell.classList.add("first");
          tr.appendChild(cell);
        }}
        tbody.appendChild(tr);
      }});
      table.appendChild(tbody);
      block.appendChild(table);
    }}
    host.appendChild(block);
  }});
}}

function render() {{
  const table = document.getElementById("per-table");
  table.innerHTML = "";
  table.appendChild(buildHead());
  table.appendChild(buildBody());
  buildReference();
}}

render();
</script>
</body>
</html>
"""


def main() -> None:
    values = fetch_values()
    parsed = parse(values)

    OUT_JSON.write_text(
        json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    html = HTML_TEMPLATE.format(
        exchange_rate=parsed["exchange_rate"] or "-",
        data_json=json.dumps(parsed, ensure_ascii=False),
    )
    OUT_HTML.write_text(html, encoding="utf-8")
    print(f"wrote {OUT_HTML}")
    print(f"wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
