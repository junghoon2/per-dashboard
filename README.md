# per-dashboard

구글 스프레드시트 **PER** 워크시트를 정적 HTML 대시보드로 빌드해 Vercel에 배포한다.

## 구조

```
build.py        # 구글 시트 → index.html 빌드 스크립트
index.html      # 빌드 산출물 (Vercel이 서빙)
per_data.json   # 파싱된 데이터 스냅샷 (디버깅용)
```

## 환경 변수

시트 ID 등 민감 식별자는 코드에 하드코딩하지 않는다. 빌드 전에 아래 변수를 설정한다.

| 변수 | 필수 | 설명 |
|------|------|------|
| `PER_SPREADSHEET_ID` | ✅ | 동기화 대상 구글 스프레드시트 ID |
| `PER_SHEET_NAME` | | 워크시트(탭) 이름. 기본 `PER` |
| `PER_CREDENTIALS_PATH` | | 서비스 계정 `credentials.json` 절대 경로. 기본은 형제 프로젝트 경로 |

`.env` 파일(루트) 자동 로드 지원. **`.env` 는 `.gitignore` 처리되어 커밋되지 않는다.**

`.env` 예시:

```dotenv
PER_SPREADSHEET_ID=여기에-실제-시트-ID
PER_SHEET_NAME=PER
```

## 빌드

```bash
# 형제 프로젝트(gsheet-toss-portfolio-sync)의 venv 재사용
/Users/jerry/private/gsheet-toss-portfolio-sync/venv/bin/python build.py
```

성공 시 `index.html`, `per_data.json` 이 갱신된다.

## 배포 (Vercel)

루트의 `index.html` 을 그대로 정적 호스팅한다. Vercel 프로젝트 설정에서:

- Framework Preset: **Other**
- Build Command: 비움 (또는 위 빌드 명령)
- Output Directory: `.` (루트)

시트 갱신 후 `python build.py` → `git push` 하면 Vercel이 자동 재배포한다.
